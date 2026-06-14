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
        self._lesion_vol: dict = {}     # demo-pathology volumes, cached per kind
        self._applied_field: Any = None  # field the engine's global tissue table is set to
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
        self.kspace_fig = Figure(figsize=(3.4, 3.4), facecolor=_C_CANVAS)
        self.kspace_ax = self.kspace_fig.add_subplot(111)
        self.psd_fig = Figure(figsize=(7.2, 3.0), facecolor=_C_PANEL)
        self.b0map_fig = Figure(figsize=(3.6, 3.6), facecolor=_C_CANVAS)
        self.b0map_ax = self.b0map_fig.add_subplot(111)
        self.gfactor_fig = Figure(figsize=(3.6, 3.6), facecolor=_C_CANVAS)
        self.gfactor_ax = self.gfactor_fig.add_subplot(111)
        self.recon_fig = Figure(figsize=(4.0, 4.0), facecolor=_C_CANVAS)
        self.recon_ax = self.recon_fig.add_subplot(111)
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
        plane = _REGION_PLANE.get(name, "axial")                 # canonical plane
        self.orientation.set(plane)
        # Sync the engine's orientation too: get_max_slice_idx() reads
        # self.sim.orientation, so without this the mid-slice and the returned
        # max_slice are computed along the *axial* axis even for a sagittal region
        # (Spine/Knee). That opened the Spine on a near-lateral slice (111/128
        # instead of the 64 midline) — a body-edge "cut in half" localizer — and
        # gave the slice slider the wrong range.
        self.sim.orientation = plane
        self.slice_idx.set(self.sim.get_max_slice_idx() // 2)
        return {"dims": self.dims(), "max_slice": self.sim.get_max_slice_idx()}

    # Precomputed brain vessel tree: the indices add_vessels_3d changes (label 11).
    # Shipped by build_web (scripts/build_brain_vessels.py) so the browser skips the
    # ~minute build that MR-angiography / SWI would otherwise stall on.
    _VESSELS_IDX = "/data/brain_vessels_idx.npy"

    def _ensure_vessels(self) -> None:
        """Make the TOF vessel tree available for the brain (MR-angiography / SWI).
        Prefer the precomputed index file (sub-millisecond reconstruction); fall
        back to building it in-process (~a minute) when the file isn't present —
        e.g. the desktop/test path. Cached so it is paid at most once."""
        name = self.region.get()
        vessels, activation = self._region_aux_cache.get(name, (None, None))
        if vessels is None and name == "Brain":
            base = self._region_cache[name]
            vessels = self._load_precomputed_vessels(base)
            if vessels is None:
                from phantom3d_extended import add_vessels_3d
                vessels = add_vessels_3d(base)
            self._region_aux_cache[name] = (vessels, activation)
        self._vessels = vessels

    def _load_precomputed_vessels(self, base: np.ndarray) -> "np.ndarray | None":
        """Rebuild the vessel volume from the shipped index file, or None if it is
        absent or doesn't match this phantom (then the caller computes it)."""
        path = self._VESSELS_IDX if os.path.exists(self._VESSELS_IDX) else \
            os.path.join(os.path.dirname(__file__), "..", "data", "brain_vessels_idx.npy")
        if not os.path.exists(path):
            return None
        try:
            idx = np.load(path)
            if idx.size == 0 or int(idx.max()) >= base.size:
                return None                          # mismatched phantom → recompute
            vessels = base.copy()
            vessels.reshape(-1)[idx] = 11            # label 11 = Blood (vessels)
            return vessels
        except Exception:
            return None

    # Demo pathologies → tissue label painted into brain white matter. Each label's
    # sequence-specific behaviour (T1/T2, restricted diffusion, paramagnetic
    # susceptibility, Gd uptake) is defined in tissue_db / phantom3d_extended /
    # b0 / rendering, keyed by these labels.
    # Single-label pathologies map kind → label. The abscess is special: a pus
    # core (27, restricted diffusion) inside an enhancing capsule/rim (28).
    # "ms" reuses the white-matter-lesion label (23, FLAIR-bright) but paints
    # several small periventricular plaques instead of one — no new tissue needed.
    _PATHOLOGY = {"lesion": 23, "stroke": 24, "hemorrhage": 25, "tumor": 26,
                  "abscess": 27, "ms": 23}
    _PATHOLOGY_R = {"lesion": 0.035, "stroke": 0.045, "hemorrhage": 0.032,
                    "tumor": 0.05, "abscess": 0.068, "ms": 0.022}

    def _pathology_volume(self, kind: str) -> np.ndarray:
        """The brain volume with a demo `kind` lesion painted in (cached per kind).
        The painting is shared with the desktop via rendering.paint_brain_pathology."""
        cached = self._lesion_vol.get(kind) if isinstance(self._lesion_vol, dict) else None
        if cached is not None:
            return cached
        import rendering
        vol = rendering.paint_brain_pathology(self._region_cache["Brain"], kind)
        self._lesion_vol[kind] = vol
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
        s.no_phase_wrap = bool(payload.get("no_phase_wrap", False))
        s.pe_swap = bool(payload.get("pe_swap", False))
        s.satband_enabled = bool(payload.get("satband_enabled", False))
        s.satband_pos = float(np.clip(payload.get("satband_pos", 50.0), 0.0, 100.0))
        s.satband_width = float(np.clip(payload.get("satband_width", 15.0), 0.0, 60.0))
        s.satband_angle = float(np.clip(payload.get("satband_angle", 0.0), -90.0, 90.0))
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

        # Demo pathology: paint a lesion into the brain when asked. Each kind is
        # revealed by a specific sequence (lesion→T2/FLAIR, stroke→DWI,
        # hemorrhage→SWI, tumor→T1+Gd). Accept the legacy `lesion: true` too.
        patho = payload.get("pathology") or ("lesion" if payload.get("lesion") else "")
        if patho in self._PATHOLOGY and region == "Brain":
            self.sim.volume = self._pathology_volume(patho)
        else:
            self.sim.volume = self._region_cache[region]

        params = default_params(**payload.get("params", {}))
        # Display each region at its native field of view so the body isn't
        # magnified — default_params' 240 mm would zoom ~1.6x into a 380 mm
        # abdomen. (The interactive in-plane FOV box is a separate crop below.)
        params["FOV"] = _NATIVE_FOV.get(region, params.get("FOV", 240.0))
        # Keep the engine's global tissue table (used by the DWI/SWI paths) synced
        # to the authoritative tissue_db at the selected field — as the desktop does
        # — so demo-pathology labels (23–26) render on those sequences too.
        field = params.get("field_strength", "3T")
        if field != self._applied_field:
            tissue_db.apply_to_engine(field)
            self._applied_field = field
        self._sync_sim(orient, sl, params["sequence"])
        self._apply_planning(payload)   # in-plane FOV box + oblique angulation
        ww = float(payload.get("window_width", 1.0))
        wl = float(payload.get("window_level", 0.5))

        image, metrics = self._acquire_or_reformat(params)
        image = self._apply_coil_shading(image, payload.get("receive_coil"))
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
            "kspace": self._draw_kspace() if payload.get("show_kspace") else None,
            "psd": self._draw_psd(params) if payload.get("show_psd") else None,
            "b0map": self._draw_b0map(orient, sl, params) if payload.get("show_b0map") else None,
            "gfactor": self._draw_gfactor(orient, sl, params) if payload.get("show_gfactor") else None,
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

    def _frac_to_pixel(self, fx: float, fy: float) -> "tuple[float, float]":
        """Map a point given as a fraction of the displayed image element
        (fx left→right, fy top→bottom) onto (col, row) of the current image
        array, undoing the letterbox the square-pixel framing introduces and the
        origin='lower' y-flip. Uses the axes box/limits left by the last render."""
        ax = self.img_ax
        pos = ax.get_position()
        x0, y0, w, h = pos.x0, pos.y0, pos.width, pos.height
        (xl0, xl1), (yl0, yl1) = ax.get_xlim(), ax.get_ylim()
        figx, figy = fx, 1.0 - fy                          # figure frac (y is bottom-up)
        ax_fx = float(np.clip((figx - x0) / w, 0.0, 1.0)) if w else 0.0
        ax_fy = float(np.clip((figy - y0) / h, 0.0, 1.0)) if h else 0.0
        col = xl0 + ax_fx * (xl1 - xl0)
        row = yl0 + ax_fy * (yl1 - yl0)                    # origin lower → ax_fy=0 at row≈0
        return col, row

    def measure(self, payload: dict) -> dict:
        """Geometry/intensity readout for the ruler and ROI tools, on the main image
        or — when ``panel`` names a reconstruction panel — on that reformat.

        payload = {kind: "ruler"|"roi", points: [[fx,fy], …], panel?: name}. Points
        are a fraction of the displayed element. ROI stats read the *real* signal
        array, so mean/SD/SNR are physically meaningful."""
        panel = payload.get("panel")
        panels = getattr(self, "_recon_panels", {})
        frac = [(float(p[0]), float(p[1])) for p in payload.get("points", [])]
        if panel and panel in panels:
            # Reconstruction panels fill their element edge-to-edge, so the fraction
            # maps straight to (col,row) (no letterbox); y is top→bottom on display.
            img, mm_per_px = panels[panel]
            Hh, Ww = img.shape
            pts = [(fx * (Ww - 1), (1.0 - fy) * (Hh - 1)) for fx, fy in frac]
        else:
            img = self.current_image
            if img is None or getattr(img, "ndim", 0) != 2:
                return {"ok": False}
            H, W = img.shape
            mm_per_px = float(_NATIVE_FOV.get(self.region.get(), 240.0)) / max(H, W)
            pts = [self._frac_to_pixel(fx, fy) for fx, fy in frac]
        import rendering
        return rendering.measure_stats(img, mm_per_px, str(payload.get("kind") or ""), pts)

    # Short, beginner-friendly names for the anatomy-label overlay.
    _ANATOMY_NAMES = {1: "CSF", 2: "Gray matter", 3: "White matter", 4: "Fat",
                      5: "Skull", 6: "Muscle", 7: "Liver", 8: "Spleen", 9: "Kidney",
                      10: "Kidney", 11: "Vessel", 13: "Bone", 14: "Marrow",
                      15: "Disc", 16: "Cord", 17: "Bowel", 18: "Lung",
                      19: "Pancreas", 20: "Heart", 21: "Soft tissue", 22: "Ligament",
                      23: "Lesion", 24: "Infarct", 25: "Haemorrhage", 26: "Tumour",
                      27: "Abscess", 28: "Rim"}

    @staticmethod
    def _interior_anchor(mask: np.ndarray) -> "tuple[int, int, int]":
        """(row, col, size) of the most interior point of `mask`'s largest
        connected component — the distance-transform peak, guaranteed to lie
        inside the component. Unlike the centroid, this sits ON the tissue even
        for ring/ribbon shapes (skull, scalp, cortex). size is the component area."""
        from scipy.ndimage import distance_transform_edt as _edt
        from scipy.ndimage import label as _cc
        cc, _ = _cc(mask)
        if cc.max() == 0:
            return 0, 0, 0
        comp = cc == 1 + int(np.argmax(np.bincount(cc.flat)[1:]))
        py, px = np.unravel_index(int(np.argmax(_edt(comp))), comp.shape)
        return int(py), int(px), int(comp.sum())

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
        try:
            lab = np.asarray(self.sim._get_phantom_slice(orient, sl, params))
        except Exception:
            return
        if lab.ndim != 2:
            return
        H, W = lab.shape
        sy, sx = img_shape[0] / H, img_shape[1] / W
        total = max(int((lab > 0).sum()), 1)
        # One placement per tissue, anchored *inside* its largest component (the
        # interior anchor sits ON the tissue, unlike the centroid).
        cands = []
        for v in np.unique(lab):
            if v == 0 or v == 12:                          # skip background / gas
                continue
            mask = lab == v
            # Demo pathologies (23–28) are small but are the point — always name
            # them; otherwise skip slivers to avoid clutter.
            if not (23 <= v <= 28) and mask.sum() < 0.012 * total:
                continue
            py, px, size = self._interior_anchor(mask)
            cands.append((size, float(px * sx), float(py * sy),
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

    # Quantitative parameter maps get a perceptually-uniform, colorblind-safe
    # colormap + a calibrated colorbar (rather than grayscale with no scale) — a
    # well-established scientific-visualization practice (rainbow/grayscale maps
    # mislead and fail for colour-vision deficiency). Weighted images stay gray.
    def _map_spec(self, params: dict) -> "tuple[str, str] | None":
        """(colormap, unit-label) when the current display is a quantitative map,
        else None (grayscale weighted image). Shared with the desktop via rendering."""
        import rendering
        return rendering.quantitative_map_spec(
            params.get("sequence", ""), params.get("qmri_display", ""),
            params.get("diff_display", ""))

    def _apply_coil_shading(self, image: np.ndarray, coil: "str | None") -> np.ndarray:
        """Modulate the image by a receive coil's spatial sensitivity (a display
        effect: shows how surface/array coils shade the picture). Uniform → no-op.
        The physics-derived envelope (coil.py) is shared with the desktop app."""
        import coil as coil_mod
        if not coil or coil == "uniform" or getattr(image, "ndim", 0) != 2:
            return image
        env = coil_mod.receive_coil_envelope(image.shape, coil)
        if env is None:
            return image
        return (np.asarray(image, dtype=np.float64) * env).astype(image.dtype)

    def _draw_image(self, img: np.ndarray, params: dict, orient: str,
                    sl_idx: int, ww: float = 1.0, wl: float = 0.5,
                    label_anatomy: bool = False) -> str:
        ax = self.img_ax
        # Drop a previous map colorbar inset (ax.clear() doesn't remove child axes).
        prev_cax = getattr(self, "_map_cax", None)
        if prev_cax is not None:
            try:
                prev_cax.remove()
            except Exception:
                pass
            self._map_cax = None
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
        vlo, vhi = center - width / 2, center + width / 2
        mapspec = self._map_spec(params)
        ax.imshow(img, cmap=(mapspec[0] if mapspec else "gray"), origin="lower",
                  aspect=1.0, vmin=vlo, vmax=vhi)
        if mapspec is not None:
            # Overlaid (inset) colorbar — keeps the image full-frame so the probe /
            # measure / window-level coordinate mapping is unaffected.
            cax = ax.inset_axes((0.905, 0.07, 0.03, 0.42))
            cax.imshow(np.linspace(1.0, 0.0, 256).reshape(-1, 1), cmap=mapspec[0],
                       aspect="auto", extent=(0.0, 1.0, vlo, vhi), vmin=0.0, vmax=1.0)
            cax.set_xticks([])
            cax.set_yticks([vlo, (vlo + vhi) / 2.0, vhi])
            cax.yaxis.set_ticks_position("right")
            cax.tick_params(axis="y", colors="#e6e9ee", labelsize=6, length=2, pad=1)
            for _s in cax.spines.values():
                _s.set_edgecolor("#3a424d")
            cax.set_title(mapspec[1], color="#e6e9ee", fontsize=6, pad=2)
            self._map_cax = cax
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

    def _draw_kspace(self) -> str:
        """Log-magnitude of the acquired k-space (the raw data the image is the
        Fourier transform of). Populated by the 2-D acquisition; the 3-D slab path
        doesn't keep a single 2-D plane, so show a note there instead."""
        from kspace import get_kspace_display
        ax = self.kspace_ax
        ax.clear(); ax.set_axis_off(); ax.set_facecolor(_C_CANVAS)
        ks = self.sim.last_kspace
        if ks is None:
            ax.text(0.5, 0.5, "k-space view is shown for 2-D acquisitions\n(turn off 3-D slab)",
                    color="#6b7585", ha="center", va="center", transform=ax.transAxes, fontsize=9)
        else:
            ax.imshow(get_kspace_display(ks), cmap="hot", origin="lower", aspect="equal")
            ax.set_title("k-space  (log |S|)", color="#9aa4b2", fontsize=8, pad=3)
        self.kspace_fig.subplots_adjust(left=0.02, right=0.98, top=0.92, bottom=0.02)
        return _png_b64(self.kspace_fig)

    def _draw_psd(self, params: dict) -> str:
        """Pulse-sequence diagram for the current sequence (RF / gradient / signal
        events on a local timeline) — reuses the desktop's psd renderers."""
        from psd import draw_psd
        self.psd_fig.clear()
        draw_psd(self.psd_fig, params["sequence"], params["TR"], params["TE"],
                 params.get("TI", 150), params.get("flip_angle", 90),
                 int(params.get("etl", 1)), params.get("echo_spacing", 10),
                 params.get("b_value", 1000))
        return _png_b64(self.psd_fig)

    def _draw_b0map(self, orient: str, sl: int, params: dict) -> str:
        """B0 off-resonance field of the current slice (Hz) — the susceptibility-
        driven inhomogeneity that warps EPI and shifts fat. Reuses the engine's
        per-slice field used for EPI distortion."""
        _B0 = {"1.5T": 1.5, "3T": 3.0, "7T": 7.0}.get(params.get("field_strength", "3T"), 3.0)
        ax = self.b0map_ax
        ax.clear(); ax.set_axis_off()
        try:
            field = np.asarray(self.sim._b0_field_slice(orient, sl, params, _B0))
        except Exception:
            ax.text(0.5, 0.5, "field map n/a", color="#6b7585", ha="center",
                    va="center", transform=ax.transAxes); return _png_b64(self.b0map_fig)
        lim = float(max(1.0, np.percentile(np.abs(field), 99)))
        im = ax.imshow(field, cmap="RdBu_r", origin="lower", vmin=-lim, vmax=lim)
        ax.set_title("B0 off-resonance (Hz)", color="#9aa4b2", fontsize=8, pad=3)
        self.b0map_fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
        self.b0map_fig.subplots_adjust(left=0.02, right=0.9, top=0.92, bottom=0.02)
        return _png_b64(self.b0map_fig)

    def _draw_gfactor(self, orient: str, sl: int, params: dict) -> str:
        """SENSE g-factor map — local noise amplification from parallel-imaging
        unfolding, which grows with the acceleration R. Reuses coil.g_factor_map."""
        import coil
        ax = self.gfactor_ax
        ax.clear(); ax.set_axis_off()
        R = int(params.get("accel_factor", 1))
        if R <= 1 or params.get("accel_method") not in ("SENSE", "GRAPPA"):
            ax.text(0.5, 0.5, "g-factor map shows parallel-imaging\nnoise — set acceleration R > 1 (SENSE)",
                    color="#6b7585", ha="center", va="center", transform=ax.transAxes, fontsize=9)
            return _png_b64(self.gfactor_fig)
        lab = np.asarray(self.sim._b0_field_slice(orient, sl, params, 3.0))   # slice geometry
        H, W = lab.shape
        Ht = (H // R) * R
        sens = coil.head_coil_array((Ht, W), n_coils=8)
        g = coil.g_factor_map(sens, R)
        im = ax.imshow(g, cmap="viridis", origin="lower", vmin=1.0,
                       vmax=float(max(1.2, np.percentile(g, 99))))
        ax.set_title(f"g-factor map (R={R})", color="#9aa4b2", fontsize=8, pad=3)
        self.gfactor_fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
        self.gfactor_fig.subplots_adjust(left=0.02, right=0.9, top=0.92, bottom=0.02)
        return _png_b64(self.gfactor_fig)

    # --- 3-D reconstruction (MPR / MIP / oblique from the acquired slab) ----- #
    @staticmethod
    def _scale_bar_mm(width_px: int, mm_per_px: float) -> float:
        """Largest tidy length (…1/2/5/10/20/50… mm) that is ≤ a quarter of the
        image, so the scale bar stays a sensible size."""
        import numpy as _np
        target = width_px * mm_per_px * 0.25
        if target < 1.0:
            return 0.0
        mag = 10.0 ** _np.floor(_np.log10(target))
        best = mag
        for step in (1.0, 2.0, 5.0, 10.0):
            if step * mag <= target:
                best = step * mag
        return best

    def _recon_png(self, arr: np.ndarray, title: str = "",
                   crosshair: "tuple[float, float] | None" = None,
                   mm_per_px: "float | None" = None) -> str:
        """Grayscale render of a 2-D reconstruction array (auto-windowed). The figure
        is sized to the array's aspect ratio and the image fills it edge-to-edge, so
        the panel keeps its **true proportions** (no stretch, no letterbox) while an
        element fraction still maps directly to a data fraction for click-to-navigate.
        Optional crosshair (fractional col,row), a calibrated scale bar (``mm_per_px``)
        and a small corner label are drawn in data/axes coordinates."""
        import numpy as _np
        a = _np.asarray(arr, dtype=float)
        H, W = a.shape
        base = 4.0
        self.recon_fig.set_size_inches((base, base * H / W) if W >= H else (base * W / H, base))
        ax = self.recon_ax
        ax.clear(); ax.set_axis_off(); ax.set_facecolor(_C_CANVAS)
        finite = a[_np.isfinite(a)]
        hi = float(_np.percentile(finite, 99)) if finite.size else 1.0
        ax.imshow(a, cmap="gray", origin="lower", aspect="auto",
                  vmin=0.0, vmax=hi if hi > 0 else 1.0)
        ax.set_xlim(-0.5, W - 0.5); ax.set_ylim(-0.5, H - 0.5)
        if crosshair is not None:
            ax.axvline(crosshair[0] * W, color="#ffdd44", lw=0.6, alpha=0.6)
            ax.axhline(crosshair[1] * H, color="#ffdd44", lw=0.6, alpha=0.6)
        if mm_per_px and mm_per_px > 0:
            bar_mm = self._scale_bar_mm(W, mm_per_px)
            if bar_mm > 0:
                bar_px = bar_mm / mm_per_px
                x0, y0 = 0.04 * W, 0.05 * H
                ax.plot([x0, x0 + bar_px], [y0, y0], color="#ffdd44", lw=2.0, solid_capstyle="butt")
                lbl = f"{bar_mm / 10:.0f} cm" if bar_mm >= 10 else f"{bar_mm:.0f} mm"
                ax.text(x0 + bar_px / 2, y0 + 0.02 * H, lbl, color="#ffdd44",
                        fontsize=7, ha="center", va="bottom")
        if title:
            ax.text(0.015, 0.985, title, transform=ax.transAxes, color="#9aa4b2",
                    fontsize=7, ha="left", va="top")
        self.recon_fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        return _png_b64(self.recon_fig)

    def reconstruct(self, payload: dict) -> dict:
        """Build a reconstruction from the acquired 3-D slab. payload = {region,
        params (with acq3d), mode: 'mpr'|'mip'|'oblique', center:[cz,cy,cx],
        mip_plane, mip_thickness, azimuth, elevation, tilt, rot}. Returns
        {ok, mode, panels:{name->dataURL}, dims}. Re-acquires the slab if needed
        so it works as a standalone call."""
        import reconstruction as rc
        params = default_params(**payload.get("params", {}))
        if not (params.get("acq3d") and params["sequence"] in _ACQ3D_SEQUENCES):
            return {"ok": False, "error": "Reconstruction needs a 3-D slab acquisition "
                    "(enable 3-D on a SE/GRE/IR/bSSFP sequence)."}
        # Acquire (or reuse) the slab via the normal render path, then operate on
        # the stored recon block.
        self.render({**payload, "show_kspace": False, "show_psd": False,
                     "show_b0map": False, "show_gfactor": False, "contrast_map": False})
        block = self.sim._recon3d
        if block is None:
            return {"ok": False, "error": "no 3-D recon block available"}
        nz, ny, nx = block.shape
        ctr = payload.get("center") or [nz // 2, ny // 2, nx // 2]
        mode = payload.get("mode", "mpr")
        # Isotropic mm per recon voxel (the block is the source grid over the region
        # FOV) — drives the scale bar on the aspect-preserving projection views.
        mm_per_px = _NATIVE_FOV.get(self.region.get(), 220.0) / max(1, nx)
        panels: dict = {}
        # Keep the raw panel arrays so the ruler / ROI tools can measure on them.
        self._recon_panels: dict = {}
        if mode == "mpr":
            tri = rc.mpr_triplanar(block, (int(ctr[0]), int(ctr[1]), int(ctr[2])))
            cross = {"axial": (ctr[2] / nx, ctr[1] / ny),
                     "coronal": (ctr[2] / nx, ctr[0] / nz),
                     "sagittal": (ctr[1] / ny, ctr[0] / nz)}
            for name, img in tri.items():
                panels[name] = self._recon_png(img, name.capitalize(), cross[name])
                self._recon_panels[name] = (np.asarray(img, dtype=float), mm_per_px)
            # 4th quadrant: a 3-D MIP overview of the whole slab (PACS-style) — an
            # oblique projection so it reads as a volume next to the three cuts.
            ov = rc.rotating_mip(block, 35.0, 20.0)
            panels["overview"] = self._recon_png(ov, "3D MIP", mm_per_px=mm_per_px)
            self._recon_panels["overview"] = (np.asarray(ov, dtype=float), mm_per_px)
        elif mode == "mip":
            plane = payload.get("mip_plane", "axial")
            thick = int(payload.get("mip_thickness", 20))
            proj = str(payload.get("mip_mode", "mip")).lower()
            # Slab centre defaults to the crosshair, but a movable position can be
            # sent explicitly (fraction 0..1 along the projection axis).
            axn = block.shape[rc.THROUGH_AXIS[plane]]
            c = (int(round(float(payload["mip_center_frac"]) * (axn - 1)))
                 if payload.get("mip_center_frac") is not None
                 else int(ctr[rc.THROUGH_AXIS[plane]]))
            arr = rc.thick_slab_projection(block, plane, c, thick, proj)
            panels["main"] = self._recon_png(
                arr, f"{proj.upper()} · {plane} · {thick}p slab", mm_per_px=mm_per_px)
            self._recon_panels["main"] = (np.asarray(arr, dtype=float), mm_per_px)
        elif mode == "rmip":
            az = float(payload.get("azimuth", 0.0)); el = float(payload.get("elevation", 0.0))
            arr = rc.rotating_mip(block, az, el)
            panels["main"] = self._recon_png(arr, f"Rotating MIP · az {az:.0f}° el {el:.0f}°",
                                             mm_per_px=mm_per_px)
            self._recon_panels["main"] = (np.asarray(arr, dtype=float), mm_per_px)
        elif mode == "oblique":
            tilt = float(payload.get("tilt", 0.0)); rot = float(payload.get("rot", 0.0))
            ob = rc.oblique_mpr(block, (ctr[0], ctr[1], ctr[2]), tilt, rot,
                                payload.get("base", "axial"))
            panels["main"] = self._recon_png(ob, f"Oblique MPR · tilt {tilt:.0f}° rot {rot:.0f}°",
                                             mm_per_px=mm_per_px)
            self._recon_panels["main"] = (np.asarray(ob, dtype=float), mm_per_px)
        else:
            return {"ok": False, "error": f"unknown reconstruction mode: {mode}"}
        return {"ok": True, "mode": mode, "panels": panels,
                "dims": {"nz": nz, "ny": ny, "nx": nx}}

    def reconstruct_cine(self, payload: dict) -> dict:
        """Pre-render a full 360° rotating-MIP cine (a stack of frames the front-end
        cycles for a smooth spin). payload like reconstruct() plus n_frames and
        elevation. Returns {ok, frames:[dataURL, ...]}."""
        import reconstruction as rc
        params = default_params(**payload.get("params", {}))
        if not (params.get("acq3d") and params["sequence"] in _ACQ3D_SEQUENCES):
            return {"ok": False, "error": "Cine needs a 3-D slab acquisition."}
        self.render({**payload, "show_kspace": False, "show_psd": False,
                     "show_b0map": False, "show_gfactor": False, "contrast_map": False})
        block = self.sim._recon3d
        if block is None:
            return {"ok": False, "error": "no 3-D recon block available"}
        n = int(np.clip(int(payload.get("n_frames", 12)), 4, 36))
        el = float(payload.get("elevation", 0.0))
        frames = [self._recon_png(rc.rotating_mip(block, i * 360.0 / n, el),
                                  f"Rotating MIP · {i * 360 // n}°")
                  for i in range(n)]
        return {"ok": True, "frames": frames}

    # --- FOV-planning scout (3-plane localizer, render-only) ---------------- #
    # (row_axis, col_axis) of each scout panel in (Z,Y,X) volume terms; the
    # remaining axis is the panel's through-plane normal.
    _PANEL_AXES = {"axial": (1, 2), "coronal": (0, 2), "sagittal": (0, 1)}
    _ACQ_AXIS = {"axial": 0, "coronal": 1, "sagittal": 2}
    # Which oblique angle each cross panel controls, so the two cross panels give
    # the two independent double-oblique degrees of freedom (tilt about col_vec,
    # rot about row_vec). Determined from which angle actually re-angles that
    # panel's slice band (see plane_from_angles / scout_band): dragging a panel's
    # band tilts the plane as seen in that very panel.
    _OBLIQUE_PANEL = {
        "axial":    {"coronal": "rot", "sagittal": "tilt"},
        "coronal":  {"axial": "rot", "sagittal": "tilt"},
        "sagittal": {"axial": "rot", "coronal": "tilt"},
    }

    def render_scout(self, payload: dict) -> str:
        """Render the 3-plane localizer with the prescription overlaid: the slice
        drawn as a band of its true thickness (the whole slab when 3-D), the FOV
        box on the acquired plane, and crosshairs through the prescribed centre."""
        import math
        from matplotlib.patches import Polygon, Rectangle
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
        sat_on = bool(payload.get("satband_enabled", False))
        sat_pos = float(np.clip(payload.get("satband_pos", 50.0), 0.0, 100.0)) / 100.0
        sat_wf = float(np.clip(payload.get("satband_width", 15.0), 0.0, 60.0)) / 100.0
        sat_ang = math.radians(float(np.clip(payload.get("satband_angle", 0.0), -90.0, 90.0)))
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
                if sat_on:                               # draggable saturation band
                    cx, cy = fb["x0"] + fb["w"] / 2.0, fb["y0"] + sat_pos * fb["h"]
                    ht = max(1.5, sat_wf * fb["h"] / 2.0)
                    ln = fb["w"] / 2.0 + 0.08 * fb["w"]
                    dx_, dy_ = math.cos(sat_ang), math.sin(sat_ang)
                    nx_, ny_ = -math.sin(sat_ang), math.cos(sat_ang)
                    corners = [(cx + sx * ln * dx_ + sy * ht * nx_,
                                cy + sx * ln * dy_ + sy * ht * ny_)
                               for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                    ax.add_patch(Polygon(corners, closed=True, facecolor="#e6b35a",
                                         alpha=0.30, edgecolor="#e6b35a", linewidth=1.0))
                    ax.plot([cx - ln * dx_, cx + ln * dx_], [cy - ln * dy_, cy + ln * dy_],
                            "s", color="#ff7733", markersize=5, markeredgecolor="white",
                            markeredgewidth=0.6)
                    ax.text(cx, cy, "SAT", color="#3a2a10", fontsize=6.5, ha="center",
                            va="center", fontweight="bold")
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
                # On-image angle gizmo: pivot at the centre + the angle this panel
                # controls, so the obliquity reads on the localizer itself.
                dof = self._OBLIQUE_PANEL[orient].get(name)
                ang_val = tilt if dof == "tilt" else (rot if dof == "rot" else 0.0)
                if dof and abs(ang_val) > 0.5 and segs and segs[mid] is not None:
                    ax.plot([fc(ctr[ca])], [ctr[ra]], "o", color="#7fb8ff", markersize=4,
                            markeredgecolor="white", markeredgewidth=0.5)
                    s = segs[mid]
                    ax.text(fc(s[2]), s[3], f"  {ang_val:+.0f}°", color="#7fb8ff",
                            fontsize=7, va="center", ha="left", fontweight="bold")
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
                entry.update(map="row", n=int(vol.shape[ra]), flip=False, role="cross",
                             angle=self._OBLIQUE_PANEL[orient].get(name))
            elif acq_axis == ca:
                entry.update(map="col", n=int(vol.shape[ca]), flip=(name == "sagittal"),
                             role="cross", angle=self._OBLIQUE_PANEL[orient].get(name))
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
                if sat_on:                    # panel-local geometry of the sat band
                    cxd = fb["x0"] + fb["w"] / 2.0
                    cyd = fb["y0"] + sat_pos * fb["h"]
                    lnd = fb["w"] / 2.0 + 0.08 * fb["w"]
                    dxe, dye = math.cos(sat_ang), math.sin(sat_ang)
                    entry["satband"] = {
                        "c": [cxd / W, 1.0 - cyd / H],
                        "e1": [(cxd - lnd * dxe) / W, 1.0 - (cyd - lnd * dye) / H],
                        "e2": [(cxd + lnd * dxe) / W, 1.0 - (cyd + lnd * dye) / H],
                        "half_t": max(1.5, sat_wf * fb["h"] / 2.0) / H,
                        "lo": 1.0 - fb["y0"] / H,
                        "hi": 1.0 - (fb["y0"] + fb["h"]) / H,
                        "wh": [int(W), int(H)],
                    }
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


def measure(payload: dict) -> dict:
    return _host().measure(payload)


def measure_json(payload_json: str) -> str:
    return json.dumps(_host().measure(json.loads(payload_json)))


def render_scout(payload: dict) -> str:
    return _host().render_scout(payload)


def render_scout_json(payload_json: str) -> str:
    h = _host()
    png = h.render_scout(json.loads(payload_json))
    return json.dumps({"scout": png, "panels": h._scout_panels})


def reconstruct(payload: dict) -> dict:
    return _host().reconstruct(payload)


def reconstruct_json(payload_json: str) -> str:
    return json.dumps(_host().reconstruct(json.loads(payload_json)))


def reconstruct_cine_json(payload_json: str) -> str:
    return json.dumps(_host().reconstruct_cine(json.loads(payload_json)))


def apply_preset(name: str) -> dict:
    """Resolve a clinical preset to a region/plane/params bundle for the JS shell."""
    p = presets_mod.get_preset(name) or {}
    return {
        "region": presets_mod.get_preset_region(name) or "Brain",
        "orientation": presets_mod.get_preset_plane(name),
        "params": dict(p),
    }
