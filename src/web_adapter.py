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
_NATIVE_FOV = {"Brain": 220.0, "Abdomen": 380.0, "Spine": 320.0,
               "Pelvis": 380.0, "Knee": 150.0, "Torso": 400.0}
# Canonical default plane per region (spine/knee read best sagittal, not axial).
_REGION_PLANE = {"Spine": "sagittal", "Knee": "sagittal"}


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
        self._lesion_vol: Any = None    # brain volume with a demo WM lesion painted in
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
        # TR×TE contrast-landscape map (optional teaching panel).
        self.cmap_fig = Figure(figsize=(7.2, 3.0), facecolor=_C_PANEL)
        self.cmap_ax = self.cmap_fig.add_subplot(111)
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
        self.orientation.set(_REGION_PLANE.get(name, "axial"))   # canonical plane
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

    def _lesion_volume(self) -> np.ndarray:
        """Return the brain volume with a single demo demyelinating lesion painted
        into periventricular white matter (label 23). Built once and cached. The
        lesion is a small sphere intersected with WM so it sits realistically in
        white matter near a ventricle, where it is visible on the default axial
        slice — and, by its tissue properties, nearly invisible on T1 yet bright
        on T2/FLAIR (the whole point of the demo)."""
        if self._lesion_vol is not None:
            return self._lesion_vol
        base = self._region_cache["Brain"]
        vol = base.copy()
        wm = vol == 3                                   # white matter
        z = vol.shape[0] // 2                           # the default axial slice
        # Pick a guaranteed-WM seed on that slice, biased lateral+anterior so the
        # lesion lands in one hemisphere's periventricular WM (not the midline).
        ys, xs = np.where(wm[z])
        if len(ys):
            y0, y1 = ys.min(), ys.max()
            cy = int(y0 + 0.40 * (y1 - y0))             # anterior-ish
            row = xs[ys == cy] if (ys == cy).any() else xs
            cx = int(np.percentile(row, 72))            # lateral, off midline
            r = max(4, int(round(min(vol.shape[1], vol.shape[2]) * 0.035)))
            zz, yy, xx = np.ogrid[:vol.shape[0], :vol.shape[1], :vol.shape[2]]
            sphere = ((zz - z) ** 2 + (yy - cy) ** 2 + (xx - cx) ** 2) <= r * r
            vol[sphere & wm] = 23
        self._lesion_vol = vol
        return vol

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

        # Demo pathology: paint a white-matter lesion into the brain when asked
        # (it nearly vanishes on T1 but lights up on T2/FLAIR — see _lesion_volume).
        if payload.get("lesion") and region == "Brain":
            self.sim.volume = self._lesion_volume()
        else:
            self.sim.volume = self._region_cache[region]

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
            "image": self._draw_image(image, params, orient, sl, ww, wl,
                                      label_anatomy=bool(payload.get("label_anatomy"))),
            "curve": self._draw_curve(params),
            "metrics": _jsonable(metrics),
            "dims": self.dims(),
            "max_slice": max_sl,
            "slice_idx": sl,
            "orientation": orient,
            "probe": self._probe_data(orient, sl, params),
            "cmap": self._draw_contrast_map(params) if payload.get("contrast_map") else None,
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
        seq = params["sequence"]
        ti, fa = params.get("TI", 150), params.get("flip_angle", 90)
        tissues = {}
        for v in np.unique(lab8):
            pr = props.get(int(v))
            if pr:
                # The pixel's predicted signal from the SAME equation the image
                # uses, so "Show the math" reproduces the picture exactly.
                sig = float(self._curve_signal(seq, pr, params["TR"], params["TE"], ti, fa))
                tissues[int(v)] = {"name": pr["name"], "T1": float(pr["T1"]),
                                   "T2": float(pr["T2"]), "PD": float(pr["PD"]),
                                   "T2star": float(pr.get("T2star", pr["T2"])),
                                   "S": abs(sig)}
        return {"labels": base64.b64encode(lab8.tobytes()).decode("ascii"),
                "h": int(H), "w": int(W), "tissues": tissues}

    # Short, beginner-friendly names for the anatomy-label overlay.
    _ANATOMY_NAMES = {1: "CSF", 2: "Gray matter", 3: "White matter", 4: "Fat",
                      5: "Skull", 6: "Muscle", 7: "Liver", 8: "Spleen", 9: "Kidney",
                      10: "Kidney", 11: "Vessel", 13: "Bone", 14: "Marrow",
                      15: "Disc", 16: "Cord", 17: "Bowel", 18: "Lung",
                      19: "Pancreas", 20: "Heart", 21: "Soft tissue", 22: "Ligament",
                      23: "Lesion"}

    @staticmethod
    def _label_rowh(h_img: float) -> float:
        """Approximate the anatomy-label text height in image pixels (the labels
        are drawn at a fixed point size on a fixed-size figure)."""
        return max(10.0, 0.030 * h_img)

    @staticmethod
    def _label_box(cx: float, cy: float, text: str, rowh: float) -> tuple:
        """Axis-aligned bounding box (x0, y0, x1, y1) a label occupies, used both
        to de-overlap labels at draw time and to regression-test that they don't."""
        half_w = 0.30 * rowh * max(len(text), 1)
        return (cx - half_w, cy - rowh * 0.55, cx + half_w, cy + rowh * 0.55)

    @staticmethod
    def _boxes_hit(a: tuple, b: tuple) -> bool:
        return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])

    def _draw_anatomy_labels(self, ax: Any, orient: str, sl: int, params: dict,
                             img_shape: tuple) -> None:
        """Label the major structures on the image by name (largest region per
        tissue) — a beginner aid so you learn what you're looking at. Uses the
        same co-registered label slice as the cursor probe."""
        import matplotlib.patheffects as _pe
        from scipy.ndimage import label as _cc
        try:
            lab = np.asarray(self.sim._get_phantom_slice(orient, sl, params))
        except Exception:
            return
        if lab.ndim != 2:
            return
        H, W = lab.shape
        sy, sx = img_shape[0] / H, img_shape[1] / W
        total = max(int((lab > 0).sum()), 1)
        # One placement per tissue, at the centroid of its largest component.
        cands = []
        for v in np.unique(lab):
            if v == 0 or v == 12:                          # skip background / gas
                continue
            mask = lab == v
            # The demo lesion (23) is small but is the point — always name it;
            # otherwise skip slivers to avoid clutter.
            if v != 23 and mask.sum() < 0.012 * total:
                continue
            cc, n = _cc(mask)
            big = 1 + int(np.argmax(np.bincount(cc.flat)[1:]))
            ys, xs = np.where(cc == big)
            cands.append((int(mask.sum()), float(xs.mean() * sx), float(ys.mean() * sy),
                          self._ANATOMY_NAMES.get(int(v), f"#{v}")))
        if not cands:
            return
        # Place biggest structures first (they keep their natural spot); nudge the
        # smaller labels vertically so names don't overlap (e.g. gray/white matter
        # share a centre, and the lesion sits inside white matter).
        cands.sort(key=lambda c: -c[0])
        Himg, Wimg = img_shape[0], img_shape[1]
        rowh = self._label_rowh(Himg)                      # ≈ text height in image px
        placed: list = []
        stroke = [_pe.withStroke(linewidth=2.4, foreground="#05080b")]
        for _size, cx, cy, text in cands:
            cx = float(np.clip(cx, 0.04 * Wimg, 0.96 * Wimg))
            ny = cy
            for k in (0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5):
                cand_y = float(np.clip(cy + k * 1.06 * rowh, rowh, Himg - rowh))
                box = self._label_box(cx, cand_y, text, rowh)
                if not any(self._boxes_hit(box, pb) for pb in placed):
                    ny = cand_y
                    placed.append(box)
                    break
            else:                                          # no clear slot — place anyway
                placed.append(self._label_box(cx, ny, text, rowh))
            ax.text(cx, ny, text, color="#ffe08a", fontsize=8.5, ha="center", va="center",
                    weight="bold", family="sans-serif", path_effects=stroke, zorder=7)

    def _draw_image(self, img: np.ndarray, params: dict, orient: str,
                    sl_idx: int, ww: float = 1.0, wl: float = 0.5,
                    label_anatomy: bool = False) -> str:
        ax = self.img_ax
        ax.clear()
        mx = float(np.max(img)) if float(np.max(img)) > 0 else 1.0
        # Auto-window to the image's robust intensity range (1st–99th percentile of
        # the foreground) so the default W/L (ww=1, wl=0.5) shows a well-windowed
        # picture instead of crushing dark tissue against a single bright pixel.
        # The W/L drag then scales (ww) / shifts (wl) the window over that range.
        nz = img[img > 1e-6]
        if nz.size:
            lo, hi = (float(v) for v in np.percentile(nz, (1.0, 99.0)))
            base, rng = lo, max(hi - lo, mx * 0.05)
        else:
            base, rng = 0.0, mx
        center, width = base + wl * rng, max(0.01, ww) * rng
        ax.imshow(img, cmap="gray", origin="lower", aspect=1.0,
                  vmin=center - width / 2, vmax=center + width / 2)
        render_overlay.frame_image_axes(ax)
        letters = render_overlay.orientation_letters(
            orient, sequence=params["sequence"], region=self.region.get())
        render_overlay.annotate_image(
            ax, params, orient, sl_idx, width, center,
            region=self.region.get(), letters=letters,
            recon_geom=getattr(self.sim, "_recon3d_geom", None))
        if label_anatomy:
            self._draw_anatomy_labels(ax, orient, sl_idx, params, img.shape)
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

    # Tissue pair whose contrast the TR×TE map shows, by region (tissue_db labels).
    _CMAP_PAIR = {"Brain": (2, 3), "Knee": (4, 1), "Spine": (1, 14),
                  "Abdomen": (4, 1), "Pelvis": (4, 1), "Torso": (4, 1)}

    def _draw_contrast_map(self, params: dict) -> str:
        """A TR×TE contrast landscape: |S_a − S_b| for a representative tissue
        pair across the whole TR/TE plane (same signal equations as the curve),
        with the current protocol marked — so you can *see* where contrast lives
        rather than reading one curve."""
        seq = params["sequence"]
        ti, fa = params.get("TI", 150), params.get("flip_angle", 90)
        tdb = tissue_db.properties(params.get("field_strength", "3T"))
        la, lb = self._CMAP_PAIR.get(self.region.get(), (2, 3))
        pa, pb = tdb.get(la), tdb.get(lb)
        ax = self.cmap_ax
        ax.clear(); ax.set_facecolor(_C_PANEL)
        ax.tick_params(colors="#c4cad2", labelsize=7)
        if pa and pb:
            trv = np.linspace(50.0, 5000.0, 150)
            tev = np.linspace(2.0, 200.0, 150)
            sa = np.abs(np.asarray(self._curve_signal(seq, pa, trv[:, None], tev[None, :], ti, fa)))
            sb = np.abs(np.asarray(self._curve_signal(seq, pb, trv[:, None], tev[None, :], ti, fa)))
            cnr = np.abs(sa - sb)
            mx = float(cnr.max()) or 1.0
            ax.imshow(cnr / mx, origin="lower", aspect="auto", cmap="magma", vmin=0, vmax=1,
                      extent=(float(tev[0]), float(tev[-1]), float(trv[0]), float(trv[-1])))
            ax.plot(params["TE"], params["TR"], "o", mfc="none", mec="#7fb8ff", ms=11, mew=2.2)
            ax.axvline(params["TE"], color="#7fb8ff", lw=0.5, alpha=0.5)
            ax.axhline(params["TR"], color="#7fb8ff", lw=0.5, alpha=0.5)
            ax.set_xlabel("TE (ms)", color="#c4cad2", fontsize=8)
            ax.set_ylabel("TR (ms)", color="#c4cad2", fontsize=8)
            ax.set_title(f"Contrast  {pa['name']} vs {pb['name']}   ·   {seq}"
                         "   (bright = high contrast)", color="#9aa4b2", fontsize=8)
        else:
            ax.text(0.5, 0.5, "contrast map n/a for this region", color="#6b7585",
                    ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
        self.cmap_fig.subplots_adjust(left=0.085, right=0.985, top=0.88, bottom=0.17)
        return _png_b64(self.cmap_fig)

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
    from version import __version__
    h = _host()
    return {"regions": WEB_REGIONS, "presets": presets_mod.get_preset_names(),
            "dims": h.dims(), "max_slice": h.sim.get_max_slice_idx(),
            "version": __version__}


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
