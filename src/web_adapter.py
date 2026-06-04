"""Qt-free browser/Pyodide adapter.

Drives the unchanged ``Simulator`` plus the shared, Qt-free renderers and returns
**base64 PNGs + JSON metrics** for a JavaScript front-end (the browser build runs
this module inside Pyodide). No Qt and no application window — the desktop UI's
``CurvesMixin`` is composed onto a plain headless host, and the image overlay
comes from ``render_overlay``, so the browser draws an identical viewport from the
same tested code the desktop uses.

Public surface the JS shell (and the headless tests) call:
    init()                         -> {regions, presets, sequences}
    set_region(name)               -> {dims, max_slice}
    render(payload: dict)          -> {image, curve, metrics, dims, max_slice}
    render_json(payload_json: str) -> json str   (Pyodide convenience)
    apply_preset(name)             -> {region, orientation, params}
"""
import base64
import io
import json
from typing import Any

import matplotlib
matplotlib.use("Agg")          # headless; no GUI backend in the browser
import numpy as np
from matplotlib.figure import Figure

import render_overlay
import body_phantoms
import brainweb_loader
import presets as presets_mod
from app_curves import CurvesMixin
from simulator import Simulator, default_params, _ACQ3D_SEQUENCES

# Regions offered in the web build: real brain + the synthetic body phantoms
# (no multi-GB dataset download). Real TotalSegmentator body is desktop-only.
WEB_REGIONS = ["Brain", "Abdomen", "Knee", "Spine", "Pelvis"]
_BODY_REGIONS = render_overlay.BODY_REGIONS
_C_PANEL = "#11151a"
_C_CANVAS = "#050607"
# Physical in-plane FOV (mm) per region — same map as app_qt._get_native_fov.
_NATIVE_FOV = {"Brain": 220.0, "Abdomen": 380.0, "Spine": 380.0,
               "Pelvis": 380.0, "Knee": 150.0, "Torso": 400.0}


class _Var:
    """Minimal stand-in for the desktop's ``Var`` — a value the render mixins read
    via ``.get()``. Kept local so the adapter has no Qt/app dependency."""
    __slots__ = ("_v",)

    def __init__(self, v: Any) -> None:
        self._v = v

    def get(self) -> Any:
        return self._v

    def set(self, v: Any) -> None:
        self._v = v


def _jsonable(m: dict) -> dict:
    """Coerce a metrics dict (numpy scalars / bools) to plain JSON values."""
    out: dict[str, Any] = {}
    for k, v in m.items():
        if isinstance(v, (np.floating, float)):
            out[k] = float(v)
        elif isinstance(v, (np.integer, int)):
            out[k] = int(v)
        elif isinstance(v, (np.bool_, bool)):
            out[k] = bool(v)
        else:
            out[k] = v
    return out


def _png_b64(fig: Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, facecolor=fig.get_facecolor())
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


class WebHost(CurvesMixin):
    """Headless host: the Simulator + the shared renderers, composed with the
    desktop ``CurvesMixin`` (which only needs ``axes``/``plot_curve_mode``/
    ``current_image``)."""

    def __init__(self) -> None:
        body_phantoms.merge_into_engine()      # register body tissue labels
        self.sim = Simulator()
        self.region = _Var("Brain")
        self.orientation = _Var("axial")
        self.slice_idx = _Var(90)
        self.plot_curve_mode = _Var("TE decay")
        self.current_image: Any = None
        # 3-D acquire-once / reformat cache (mirrors app_qt._acquire_or_reformat).
        self._acq3d_key: Any = None
        self._acq3d_metrics: dict = {}
        self._region_cache: dict[str, np.ndarray] = {}
        self._region_tex_cache: dict[str, Any] = {}
        self._region_aux_cache: dict[str, tuple] = {}   # (vessels, activation) per region
        self._vessels: Any = None       # TOF vessel tree (MRA), brain only
        self._activation: Any = None    # fMRI activation, brain only
        self._scout_panels: list = []   # per-panel click→slice geometry
        # Agg figures for the two panels.
        self.fig = Figure(figsize=(5.2, 5.2), facecolor=_C_CANVAS)
        self.img_ax = self.fig.add_axes((0.0, 0.0, 1.0, 1.0))
        self.curve_fig = Figure(figsize=(5.4, 3.8), facecolor=_C_PANEL)
        self.curve_ax = self.curve_fig.add_subplot(111)
        self.axes = [self.img_ax, self.curve_ax]   # CurvesMixin draws on axes[1]
        # 3-plane localizer (FOV planning) — one row of three panels.
        self.scout_fig = Figure(figsize=(7.8, 2.8), facecolor=_C_CANVAS)
        self.scout_axes = self.scout_fig.subplots(1, 3)
        self.load_region("Brain")

    # --- anatomy ------------------------------------------------------------ #
    def load_region(self, name: str) -> dict:
        if name not in self._region_cache:
            if name == "Brain":
                try:
                    vol = brainweb_loader.load_brainweb_phantom(4)
                except Exception:
                    from phantom3d import generate_synthetic_3d_brain
                    vol = generate_synthetic_3d_brain()
                tex = None
            else:
                vol = body_phantoms.build_region(name)
                tex = body_phantoms.build_region_texture(name)
                # Body phantoms are built neurological; mirror L/R (axis 2) to
                # match the radiological brain — same as app_regions.on_region_change.
                if name in _BODY_REGIONS:
                    vol = np.ascontiguousarray(np.flip(vol, axis=2))
                    if tex is not None:
                        tex = np.ascontiguousarray(np.flip(tex, axis=2))
            self._region_cache[name] = vol
            self._region_tex_cache[name] = tex
            # fMRI activation is cheap; build it once per brain. The TOF vessel
            # tree (add_vessels_3d) is *expensive* (~minute), so it is built
            # lazily on the first MR-Angiography render (see _ensure_vessels).
            if name == "Brain":
                from phantom3d_extended import add_activation_3d
                self._region_aux_cache[name] = (None, add_activation_3d(vol))
            else:
                self._region_aux_cache[name] = (None, None)
        self.region.set(name)
        vol = self._region_cache[name]
        self.sim.volume = vol
        self.sim.texture = self._region_tex_cache.get(name)
        _vessels, self._activation = self._region_aux_cache[name]
        self._vessels = _vessels
        self._acq3d_key = None                 # new anatomy invalidates the slab
        self.orientation.set("axial")
        self.slice_idx.set(self.sim.get_max_slice_idx() // 2)
        return {"dims": self.dims(), "max_slice": self.sim.get_max_slice_idx()}

    def _ensure_vessels(self) -> None:
        """Build the TOF vessel tree on demand (it is ~a minute, so we avoid
        paying it unless an MR-Angiography render actually needs it). Cached on
        the brain region so it is built at most once."""
        name = self.region.get()
        vessels, activation = self._region_aux_cache.get(name, (None, None))
        if vessels is None and name == "Brain":
            from phantom3d_extended import add_vessels_3d
            vessels = add_vessels_3d(self._region_cache[name])
            self._region_aux_cache[name] = (vessels, activation)
        self._vessels = vessels

    def _sync_sim(self, orient: str, sl_idx: int, sequence: str = "") -> None:
        """Push the current view/aux state onto the Simulator before a render —
        the web equivalent of app_qt._sync_sim (no FOV-planning / oblique here)."""
        if sequence in ("MR Angiography", "Susceptibility (SWI)"):
            self._ensure_vessels()   # SWI darkens the venous tree too
        s = self.sim
        s.orientation = orient
        s.slice_idx = sl_idx
        s.vessels = self._vessels
        s.activation = self._activation
        s.real_tof = None
        s.native_fov = _NATIVE_FOV.get(self.region.get(), 220.0)
        s.fov_planning = False
        s.tilt = 0.0
        s.rot = 0.0
        s.inplane_fov_pct = 100.0
        s.inplane_off = 0.0

    def dims(self) -> dict:
        v = self.sim.volume
        assert v is not None
        return {"axial": int(v.shape[0]), "coronal": int(v.shape[1]),
                "sagittal": int(v.shape[2])}

    # --- 3-D acquire-once / reformat (mirrors app_qt._acquire_or_reformat) --- #
    def _acquire_or_reformat(self, params: dict) -> "tuple[np.ndarray, dict]":
        if not (params.get("acq3d") and params["sequence"] in _ACQ3D_SEQUENCES):
            return self.sim.simulate(params)
        key = tuple((k, repr(v)) for k, v in sorted(params.items()) if k != "acq3d")
        orient, sl = self.orientation.get(), self.slice_idx.get()
        if key == self._acq3d_key and self.sim._recon3d is not None:
            img = self.sim.reslice_3d(orient, sl)
            if img is not None:
                return img, self._acq3d_metrics
        img, m = self.sim.simulate(params)
        self._acq3d_key, self._acq3d_metrics = key, m
        return img, m

    # --- render ------------------------------------------------------------- #
    def render(self, payload: dict) -> dict:
        """payload = {region, orientation, slice_idx, curve_mode, params:{overrides}}.
        Returns {image, curve, metrics, dims, max_slice} with images as data URLs."""
        region = payload.get("region", self.region.get())
        if region != self.region.get():
            self.load_region(region)
        orient = payload.get("orientation", self.orientation.get())
        self.orientation.set(orient)
        max_sl = self.sim.get_max_slice_idx()
        sl = int(np.clip(int(payload.get("slice_idx", self.slice_idx.get())), 0, max_sl))
        self.slice_idx.set(sl)
        self.plot_curve_mode.set(payload.get("curve_mode", "TE decay"))

        params = default_params(**payload.get("params", {}))
        self._sync_sim(orient, sl, params["sequence"])
        ww = float(payload.get("window_width", 1.0))
        wl = float(payload.get("window_level", 0.5))

        image, metrics = self._acquire_or_reformat(params)
        self.current_image = image
        return {
            "image": self._draw_image(image, params, orient, sl, ww, wl),
            "curve": self._draw_curve(params),
            "metrics": _jsonable(metrics),
            "dims": self.dims(),
            "max_slice": max_sl,
            "slice_idx": sl,
            "orientation": orient,
        }

    def _draw_image(self, img: np.ndarray, params: dict, orient: str,
                    sl_idx: int, ww: float = 1.0, wl: float = 0.5) -> str:
        ax = self.img_ax
        ax.clear()
        mx = float(np.max(img)) if float(np.max(img)) > 0 else 1.0
        center, width = wl * mx, max(0.01, ww) * mx   # window/level (normalised)
        ax.imshow(img, cmap="gray", origin="lower", aspect=1.0,
                  vmin=center - width / 2, vmax=center + width / 2)
        render_overlay.frame_image_axes(ax)
        letters = render_overlay.orientation_letters(
            orient, sequence=params["sequence"], region=self.region.get())
        render_overlay.annotate_image(
            ax, params, orient, sl_idx, width, center,
            region=self.region.get(), letters=letters,
            recon_geom=getattr(self.sim, "_recon3d_geom", None))
        return _png_b64(self.fig)

    def _draw_curve(self, params: dict) -> str:
        ax = self.curve_ax
        ax.clear()
        ax.set_facecolor(_C_PANEL)
        ax.tick_params(colors="#c4cad2", labelsize=8)
        for sp in ax.spines.values():
            sp.set_color("#252c34")
        ax.grid(True, color="#1b222a", linewidth=0.6)
        self._plot_curves(params)              # shared desktop curve code
        return _png_b64(self.curve_fig)

    # --- FOV-planning scout (3-plane localizer, render-only) ---------------- #
    # (row_axis, col_axis) of each scout panel in (Z,Y,X) volume terms; the
    # remaining axis is the panel's through-plane normal.
    _PANEL_AXES = {"axial": (1, 2), "coronal": (0, 2), "sagittal": (0, 1)}
    _ACQ_AXIS = {"axial": 0, "coronal": 1, "sagittal": 2}

    def render_scout(self, payload: dict) -> str:
        """Render the 3-plane localizer with the current slice marked on the two
        cross panels and the acquired plane framed — the FOV-planning view."""
        from oblique import three_scouts
        from phantom3d import simulate_slice
        region = payload.get("region", self.region.get())
        if region != self.region.get():
            self.load_region(region)
        orient = payload.get("orientation", self.orientation.get())
        vol = self.sim.volume
        assert vol is not None
        nz, ny, nx = vol.shape
        max_sl = self.sim.get_max_slice_idx()
        sl = int(np.clip(int(payload.get("slice_idx", self.slice_idx.get())), 0, max_sl))
        ctr = {"axial": (sl, ny // 2, nx // 2), "coronal": (nz // 2, sl, nx // 2),
               "sagittal": (nz // 2, ny // 2, sl)}[orient]
        scouts = three_scouts(vol, ctr)
        acq_axis = self._ACQ_AXIS[orient]
        names = ["axial", "coronal", "sagittal"]

        for ax, name in zip(self.scout_axes, names, strict=True):
            ax.clear(); ax.set_axis_off(); ax.set_facecolor(_C_CANVAS)
            bg = scouts[name]
            if name == "sagittal":
                bg = np.fliplr(bg)
            ax.imshow(simulate_slice(bg, 600, 12, "SE"), cmap="gray",
                      origin="lower", aspect="auto")
            ra, ca = self._PANEL_AXES[name]
            if acq_axis == ra:                          # slice cuts along a row
                ax.axhline(sl, color="#ffdd44", lw=1.6)
            elif acq_axis == ca:                        # slice cuts along a column
                col = (ny - 1 - sl) if name == "sagittal" else sl
                ax.axvline(col, color="#ffdd44", lw=1.6)
            else:                                        # this panel IS the plane
                for sp in ax.spines.values():
                    sp.set_visible(True); sp.set_color("#ffdd44"); sp.set_linewidth(2.2)
                ax.set_axis_on(); ax.set_xticks([]); ax.set_yticks([])
            ax.set_title(name.capitalize(), color="#9aa4b2", fontsize=8, pad=2)
        self.scout_fig.subplots_adjust(left=0.01, right=0.99, top=0.9, bottom=0.02, wspace=0.04)

        # Per-panel geometry so the front-end can map a click → a new slice along
        # the acquisition through-axis. box = [left, top, right, bottom] in image
        # fraction (y from the top); map says whether a click's row or column sets
        # the slice (or "none" for the acquired plane itself).
        panels = []
        for ax, name in zip(self.scout_axes, names, strict=True):
            ra, ca = self._PANEL_AXES[name]
            pos = ax.get_position()
            box = [float(pos.x0), float(1.0 - pos.y1), float(pos.x1), float(1.0 - pos.y0)]
            if acq_axis == ra:
                mp, n, flip = "row", int(vol.shape[ra]), False
            elif acq_axis == ca:
                mp, n, flip = "col", int(vol.shape[ca]), (name == "sagittal")
            else:
                mp, n, flip = "none", 0, False
            panels.append({"name": name, "box": box, "map": mp, "n": n, "flip": flip})
        self._scout_panels = panels
        return _png_b64(self.scout_fig)


# --- module-level API the JS shell / tests call ----------------------------- #
_HOST: "WebHost | None" = None


def _host() -> WebHost:
    global _HOST
    if _HOST is None:
        _HOST = WebHost()
    return _HOST


def init() -> dict:
    """Boot the host (loads the brain) and report the available choices."""
    h = _host()
    return {"regions": WEB_REGIONS, "presets": presets_mod.get_preset_names(),
            "dims": h.dims(), "max_slice": h.sim.get_max_slice_idx()}


def set_region(name: str) -> dict:
    return _host().load_region(name)


def render(payload: dict) -> dict:
    return _host().render(payload)


def render_json(payload_json: str) -> str:
    return json.dumps(_host().render(json.loads(payload_json)))


def render_scout(payload: dict) -> str:
    return _host().render_scout(payload)


def render_scout_json(payload_json: str) -> str:
    h = _host()
    png = h.render_scout(json.loads(payload_json))
    return json.dumps({"scout": png, "panels": h._scout_panels})


def apply_preset(name: str) -> dict:
    """Resolve a clinical preset to a region/plane/params bundle for the JS shell."""
    p = presets_mod.get_preset(name) or {}
    return {
        "region": presets_mod.get_preset_region(name) or "Brain",
        "orientation": presets_mod.get_preset_plane(name),
        "params": dict(p),
    }
