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
import os
from typing import Any

import matplotlib
matplotlib.use("Agg")          # headless; no GUI backend in the browser
import numpy as np
from matplotlib.figure import Figure

import render_overlay
import body_phantoms
import brainweb_loader
import tissue_db
import presets as presets_mod
from app_curves import CurvesMixin
from simulator import Simulator, default_params, _ACQ3D_SEQUENCES

# Regions offered in the web build: real brain + the synthetic body phantoms
# (no multi-GB dataset download). Real TotalSegmentator body is desktop-only.
WEB_REGIONS = ["Brain", "Abdomen", "Spine", "Pelvis", "Torso", "Knee"]
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
        self.curve_fig = Figure(figsize=(7.2, 3.2), facecolor=_C_PANEL)
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
                atlas_file = f"/data/regions/{name}_atlas.npy"
                if os.path.exists(atlas_file):
                    # Real segmented atlas bundled + lazy-fetched for the browser.
                    vol = np.load(atlas_file)
                    tex_file = f"/data/regions/{name}_texture.npy"
                    tex = (np.load(tex_file).astype(np.float32)
                           if os.path.exists(tex_file) else None)
                else:
                    # Synthetic phantom (no real atlas — e.g. Knee), or the desktop
                    # dataset path when running outside the browser.
                    vol = body_phantoms.build_region(name)
                    tex = body_phantoms.build_region_texture(name, vol)
                # Body volumes are built neurological; mirror L/R (axis 2) to match
                # the radiological brain — same as app_regions.on_region_change.
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

    def _apply_planning(self, payload: dict) -> None:
        """When the FOV-planning localizer is active, push its in-plane FOV box
        (graphic shrink/shift of the acquired field) and oblique tilt/rot angles
        onto the Simulator so the main image reflects the prescription. The engine
        already honours these via scan_geometry.fov_crop + oblique sampling; here
        we just relay the localizer's state (mirrors app_qt._sync_sim's planning)."""
        if not payload.get("fov_planning"):
            return
        s = self.sim
        s.fov_planning = True
        s.inplane_fov_pct = float(np.clip(payload.get("inplane_fov_pct", 100.0), 20.0, 100.0))
        s.inplane_off = float(payload.get("inplane_off", 0.0))
        s.tilt = float(np.clip(payload.get("tilt", 0.0), -45.0, 45.0))
        s.rot = float(np.clip(payload.get("rot", 0.0), -45.0, 45.0))

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
        # Display each region at its native field of view so the body isn't
        # magnified — default_params' 240 mm would zoom ~1.6x into a 380 mm
        # abdomen. (The interactive in-plane FOV box is a separate crop below.)
        params["FOV"] = _NATIVE_FOV.get(region, params.get("FOV", 240.0))
        self._sync_sim(orient, sl, params["sequence"])
        self._apply_planning(payload)   # in-plane FOV box + oblique angulation
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
            "probe": self._probe_data(orient, sl, params),
        }

    def _probe_data(self, orient: str, sl: int, params: dict) -> "dict | None":
        """A compact label map of the displayed slice + a tissue table (name,
        T1/T2/PD at the current field), so the front-end can show what's under the
        cursor with no server round-trip. The label slice carries the same
        FOV-crop/oblique geometry as the rendered image (sim._get_phantom_slice)."""
        try:
            lab = np.asarray(self.sim._get_phantom_slice(orient, sl, params))
        except Exception:
            return None
        if lab.ndim != 2:
            return None
        cap = 160                                  # keep the payload small
        step = max(1, int(np.ceil(max(lab.shape) / cap)))
        lab8 = np.clip(lab[::step, ::step], 0, 255).astype(np.uint8)
        H, W = lab8.shape
        props = tissue_db.properties(params.get("field_strength", "3T"))
        tissues = {}
        for v in np.unique(lab8):
            pr = props.get(int(v))
            if pr:
                tissues[int(v)] = {"name": pr["name"], "T1": float(pr["T1"]),
                                   "T2": float(pr["T2"]), "PD": float(pr["PD"])}
        return {"labels": base64.b64encode(lab8.tobytes()).decode("ascii"),
                "h": int(H), "w": int(W), "tissues": tissues}

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
        # Keep axis labels off the edges at the wide, short web aspect.
        self.curve_fig.subplots_adjust(left=0.085, right=0.985, top=0.9, bottom=0.17)
        return _png_b64(self.curve_fig)

    # --- FOV-planning scout (3-plane localizer, render-only) ---------------- #
    # (row_axis, col_axis) of each scout panel in (Z,Y,X) volume terms; the
    # remaining axis is the panel's through-plane normal.
    _PANEL_AXES = {"axial": (1, 2), "coronal": (0, 2), "sagittal": (0, 1)}
    _ACQ_AXIS = {"axial": 0, "coronal": 1, "sagittal": 2}

    def render_scout(self, payload: dict) -> str:
        """Render the 3-plane localizer with the prescription overlaid: the slice
        drawn as a band of its true thickness (the whole slab when 3-D), the FOV
        box on the acquired plane, and crosshairs through the prescribed centre."""
        from matplotlib.patches import Rectangle
        from oblique import three_scouts
        from phantom3d import simulate_slice
        import scan_geometry as sg
        region = payload.get("region", self.region.get())
        if region != self.region.get():
            self.load_region(region)
        orient = payload.get("orientation", self.orientation.get())
        vol = self.sim.volume
        assert vol is not None
        nz, ny, nx = vol.shape
        max_sl = self.sim.get_max_slice_idx()
        sl = int(np.clip(int(payload.get("slice_idx", self.slice_idx.get())), 0, max_sl))
        p = payload.get("params", {})
        acq_axis = self._ACQ_AXIS[orient]
        names = ["axial", "coronal", "sagittal"]
        amber, dim = "#ffdd44", "#6f7886"

        # In-plane FOV box (square fraction) + its centre offset along the
        # acquired plane's in-plane axis; the crosshair follows that centre.
        fov_frac = float(np.clip(payload.get("inplane_fov_pct", 100.0), 20.0, 100.0)) / 100.0
        ip_axis = sg.SCOUT[orient]["inplane_axis"]
        ip_off = float(payload.get("inplane_off", 0.0))
        tilt = float(payload.get("tilt", 0.0))
        rot = float(payload.get("rot", 0.0))
        ctr = [nz // 2, ny // 2, nx // 2]
        ctr[acq_axis] = sl
        ctr[ip_axis] = int(np.clip(vol.shape[ip_axis] / 2.0 + ip_off, 0, vol.shape[ip_axis] - 1))
        scouts = three_scouts(vol, tuple(ctr))

        # Acquisition-plane normal (with oblique tilt/rot) + per-region voxel
        # size, then the true slab / multi-slice band projected onto each scout
        # via the companion oblique.scout_band — the same geometry the desktop
        # localizer uses. A 3-D slab is one band n_partitions voxels thick; a 2-D
        # acquisition is n_slices parallel slices of slice_thickness with a gap.
        from oblique import plane_from_angles, scout_band
        native_fov = _NATIVE_FOV.get(region, 220.0)
        voxel_mm = native_fov / float(nx)
        normal = plane_from_angles(orient, tilt_deg=tilt, rot_deg=rot)[0]
        acq3d = bool(p.get("acq3d")) and p.get("sequence") in _ACQ3D_SEQUENCES
        if acq3d:
            n_eff = 1
            thick_mm, gap_mm = int(p.get("n_partitions", 16)) * voxel_mm, 0.0
            band_lbl = f"slab · {int(p.get('n_partitions', 16))}p"
        else:
            n_eff = int(np.clip(int(p.get("n_slices", 1)), 1, 32))
            thick_mm = float(p.get("slice_thickness", 5))
            gap_mm = float(p.get("slice_gap", 0.0))
            band_lbl = f"{n_eff} × {thick_mm:.0f} mm" if n_eff > 1 else f"{thick_mm:.0f} mm"
        band = scout_band(vol.shape, normal,
                          (float(ctr[0]), float(ctr[1]), float(ctr[2])),
                          n_slices=n_eff, thickness_mm=thick_mm, gap_mm=gap_mm,
                          voxel_size=(voxel_mm, voxel_mm, voxel_mm))

        for ax, name in zip(self.scout_axes, names, strict=True):
            ax.clear(); ax.set_axis_off(); ax.set_facecolor(_C_CANVAS)
            bg = scouts[name]
            if name == "sagittal":
                bg = np.fliplr(bg)
            H, W = bg.shape
            ax.imshow(simulate_slice(bg, 600, 12, "SE"), cmap="gray",
                      origin="lower", aspect="auto")
            ra, ca = self._PANEL_AXES[name]
            title = name.capitalize()
            fc = (lambda c: ny - 1 - c) if name == "sagittal" else (lambda c: c)
            # crosshair through the prescribed centre (x flips for sagittal Y)
            ax.axvline(fc(ctr[ca]), color=dim, lw=0.6, alpha=0.5)
            ax.axhline(ctr[ra], color=dim, lw=0.6, alpha=0.5)
            if name == orient:                           # this panel IS the plane
                fb = sg.inplane_box(orient, vol.shape, fov_frac, ip_off)
                ax.add_patch(Rectangle((fb["x0"], fb["y0"]), fb["w"], fb["h"],
                             fill=False, edgecolor=amber, linewidth=1.8, linestyle=(0, (4, 2))))
                for spn in ax.spines.values():
                    spn.set_visible(True); spn.set_color("#2a323c"); spn.set_linewidth(1.2)
                ax.set_axis_on(); ax.set_xticks([]); ax.set_yticks([])
                title = f"{name.capitalize()}  ·  {band_lbl}"
            else:                                        # cross panel: the slab band
                ov = band[name]
                e0, e1 = ov["edges"]
                if e0 and e1:                            # shade the slab coverage
                    ax.fill([fc(e0[0]), fc(e0[2]), fc(e1[2]), fc(e1[0])],
                            [e0[1], e0[3], e1[3], e1[1]], color=amber, alpha=0.16, lw=0)
                segs = ov["slices"]; mid = len(segs) // 2
                for j, seg in enumerate(segs):
                    if seg is None:
                        continue
                    ax.plot([fc(seg[0]), fc(seg[2])], [seg[1], seg[3]], color=amber,
                            lw=1.5 if j == mid else 0.8, alpha=0.95 if j == mid else 0.6)
            ax.set_xlim(-0.5, W - 0.5); ax.set_ylim(-0.5, H - 0.5)   # band can't expand the view
            ax.set_title(title, color="#9aa4b2", fontsize=8, pad=2)
        self.scout_fig.subplots_adjust(left=0.01, right=0.99, top=0.9, bottom=0.02, wspace=0.04)

        # Per-panel geometry for the front-end: click→slice on the cross panels,
        # plus the FOV-box rect (image fraction) on the acquired-plane panel so it
        # can be dragged. box = [left, top, right, bottom] in figure fraction.
        panels = []
        for ax, name in zip(self.scout_axes, names, strict=True):
            ra, ca = self._PANEL_AXES[name]
            pos = ax.get_position()
            box = [float(pos.x0), float(1.0 - pos.y1), float(pos.x1), float(1.0 - pos.y0)]
            entry: dict = {"name": name, "box": box}
            if acq_axis == ra:
                entry.update(map="row", n=int(vol.shape[ra]), flip=False, role="cross")
            elif acq_axis == ca:
                entry.update(map="col", n=int(vol.shape[ca]), flip=(name == "sagittal"),
                             role="cross")
            else:
                fb = sg.inplane_box(orient, vol.shape, fov_frac, ip_off)
                H, W = scouts[name].shape          # panel image is H rows × W cols
                # ip_dir/ip_sign: which panel screen axis is the in-plane (offset)
                # axis, and the sign relating a downward/rightward drag to +off.
                ip_dir, ip_sign = {"axial": ("x", 1), "coronal": ("x", 1),
                                   "sagittal": ("y", -1)}[orient]
                entry.update(map="none", n=0, flip=False, role="acq",
                             ip_axis_len=int(vol.shape[ip_axis]),
                             ip_dir=ip_dir, ip_sign=ip_sign,
                             fov_box=[fb["x0"] / W, 1.0 - (fb["y0"] + fb["h"]) / H,
                                      fb["w"] / W, fb["h"] / H])
            panels.append(entry)
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
