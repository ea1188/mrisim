"""
simulator.py — Qt-free MRI acquisition controller.

Holds the simulation pipeline that was previously embedded in the PyQt widget:
given a parameter dict (plus the active volume and view/geometry state set as
attributes), `Simulator.simulate(params)` returns `(image, metrics)`. No Qt,
no matplotlib — so the orchestration of every physics module can be unit tested.

The GUI (app_qt.MRISimulator) owns a Simulator instance, syncs the active volume
and view state onto it, and delegates simulate/slice calls here.

Volume axis convention matches phantom3d.get_slice: axis0=Z, axis1=Y, axis2=X.
"""

import numpy as np
from scipy.ndimage import gaussian_filter

from phantom3d import get_slice
from kspace import simulate_acquisition
from fse import simulate_fse_image
import flow
from artifacts import (add_motion_artifact, add_chemical_shift_artifact,
                       add_susceptibility_artifact, add_zipper_artifact,
                       calculate_chemical_shift_pixels)
from phantom3d_extended import (simulate_diffusion_3d_slice, simulate_adc_map_3d,
                                simulate_fa_map_3d, simulate_tof_3d_slice,
                                simulate_fmri_3d_slice, compute_activation_map_3d,
                                compute_tstat_map_3d, simulate_tof_with_real_data)
from presets import estimate_sar

import tissue_db
import qmri
import rendering
import rician
import b0
import angiography
import scan_geometry as sg


# Field-strength label → Tesla (labels match tissue_db.FIELD_STRENGTHS).
_B0_MAP: dict[str, float] = {"1.5T": 1.5, "3T": 3.0}

# Partial-Fourier fractions (string label → actual fraction).
_PF_MAP: dict[str, float] = {
    "Full": 1.0, "7/8": 7.0 / 8.0, "6/8": 6.0 / 8.0, "5/8": 5.0 / 8.0,
}


def _slice_profile_weights(n: int) -> np.ndarray:
    """Through-slice weighting for an imperfect (non-rectangular) RF slice profile.

    A real slice-select pulse excites the centre of the slab fully and tapers
    toward the edges, so the displayed slice is a centre-weighted average of the
    sub-slices, not a flat mean. Returns ``n`` normalised Gaussian-ish weights.
    """
    if n <= 1:
        return np.ones(1)
    idx = np.arange(n) - (n - 1) / 2.0
    w = np.exp(-0.5 * (idx / max(n / 3.0, 0.5)) ** 2)
    return w / w.sum()


def _crosstalk_snr_factor(n_slices: int, slice_gap: float, thickness: int) -> float:
    """SNR loss from slice cross-talk in contiguous 2-D multi-slice imaging.

    With several slices and little or no gap, each slice-select pulse partially
    saturates the edges of its neighbours, reducing signal. The loss is largest
    at zero gap and falls off as the gap approaches the slice thickness; a single
    slice (or a large gap) has none. Returns a factor in (0, 1].
    """
    if n_slices <= 1:
        return 1.0
    loss = 0.20 * np.exp(-float(slice_gap) / max(0.5 * thickness, 1.0))
    return float(1.0 - loss)


def _accel_gfactor(R: int, method: str) -> float:
    """Effective noise-amplification (g-factor) for an R-fold accelerated scan.

    A successful parallel-imaging / CS reconstruction keeps full resolution and
    contrast; the only image cost is an SNR drop of g·√R. The g-factor depends
    on the method: SENSE uses the coil-geometry g; GRAPPA's autocalibration
    makes it a little lower; compressed sensing has no coil g-penalty (g≈1, it
    trades incoherent residue for SNR instead). Returns 1.0 for R ≤ 1.
    """
    if R <= 1:
        return 1.0
    g = rendering.g_factor(R)
    if method == "GRAPPA":
        return 1.0 + 0.8 * (g - 1.0)
    if method == "CS":
        return 1.0
    return g


def default_params(**overrides) -> dict:
    """A complete params dict for Simulator.simulate(), with sensible defaults.

    This is the input contract for headless/scripted use — override any subset:

        sim.simulate(default_params(sequence="Gradient Echo", TE=30, flip_angle=20))

    Mirrors the parameter set the GUI assembles from its controls.
    """
    p = dict(
        sequence="Spin Echo", TR=500.0, TE=15.0, TI=2548.0, flip_angle=90.0,
        matrix_size=256, FOV=240.0, fov_fraction=100, bandwidth=125.0, NEX=1,
        slice_thickness=1, accel_factor=1, accel_method="SENSE",
        etl=16, echo_spacing=10.0,
        b_value=1000.0, diff_direction="Left-Right", diff_display="DWI",
        angio_type="TOF", angio_mip_slab=20, angio_azimuth=0, angio_elevation=0,
        angio_fast=False,
        fmri_display="EPI Image", fmri_volumes=100, fmri_threshold=3.0,
        qmri_display="T1 Map (VFA)",
        field_strength="3T", contrast_enabled=False, contrast_dose=1,
        motion_enabled=False, motion_type="periodic", motion_amplitude=3.0,
        chemical_shift_enabled=False, susceptibility_enabled=False,
        susceptibility_strength=3.0, zipper_enabled=False, snr_level=35.0,
        pf_enabled=False, pf_fraction="Full",
        kspace_filter_enabled=False, kspace_filter_window="hamming",
        b1_inhom_enabled=False, mt_enabled=False, mt_power=50,
        epi_b0_hz=60, epi_esp=5, epi_ghost=10, epi_correct_ghost=False,
        rician_bias_correction=False, pv_sigma=10,
        flow_enabled=True, flow_velocity=70,
        n_slices=1, slice_gap=0.0,
    )
    p.update(overrides)
    return p


class Simulator:
    """Pure simulation controller. Set the volume + view attributes, call simulate()."""

    # SNR reference protocol (240 FOV / 256 matrix / 5 mm slice, 125 kHz BW)
    VOX_REF = (240.0 / 256.0) ** 2 * 5.0
    BW_REF = 125000.0

    def __init__(self) -> None:
        # Active volumes (set by the caller)
        self.volume: np.ndarray | None = None        # phantom_3d
        self.vessels: np.ndarray | None = None        # phantom_3d_vessels (MRA)
        self.activation: np.ndarray | None = None      # activation_3d (fMRI)
        self.real_tof: np.ndarray | None = None
        self.texture: np.ndarray | None = None          # real-MRI detail field (body regions)
        self.native_fov: float = 220.0

        # View / geometry state (set by the caller before simulate)
        self.orientation: str = "axial"
        self.slice_idx: int = 90
        self.fov_planning: bool = False
        self.tilt: float = 0.0
        self.rot: float = 0.0
        self.inplane_fov_pct: float = 100.0
        self.inplane_off: float = 0.0

        # Caches / outputs
        self._b0_cache: tuple | None = None
        self._tof_cache: tuple | None = None
        self.last_kspace: np.ndarray | None = None

    def _tof_volume(self, TR: float, TE: float, FA: float) -> np.ndarray:
        """3D TOF intensity volume for the rotating MIP, cached.

        Built from the subject's synthetic vessel labels: blood is bright inflow
        and stationary tissue is strongly suppressed, giving a clean
        vessels-on-black angiogram. (The real TOF dataset was tried but its fat /
        skull is as bright as the vessels and can't be isolated without
        segmentation, so its MIP is hazy — the synthetic tree projects cleaner.)
        """
        vol = self.vessels
        key = (vol.shape, int(vol.sum()), round(TR, 1), round(TE, 1), round(FA, 1))
        if self._tof_cache is None or self._tof_cache[0] != key:
            self._tof_cache = (key, angiography.tof_intensity_volume(vol, TR, TE, FA))
        return self._tof_cache[1]

    # --- geometry -----------------------------------------------------------
    def get_max_slice_idx(self) -> int:
        dims = {"axial": self.volume.shape[0],
                "sagittal": self.volume.shape[2],
                "coronal": self.volume.shape[1]}
        return dims[self.orientation] - 1

    def _compute_slab_center(self, orient: str, sl_idx: int) -> np.ndarray:
        """(Z, Y, X) voxel-index centre of the currently prescribed slab."""
        vol = self.volume
        nZ, nY, nX = vol.shape
        cfg = sg.cfg_for(orient)
        center = np.array([nZ / 2.0, nY / 2.0, nX / 2.0])
        center[cfg["through_axis"]] = float(sl_idx)
        center[cfg["inplane_axis"]] = vol.shape[cfg["inplane_axis"]] / 2.0 + self.inplane_off
        return center

    def _get_phantom_slice(self, orient: str, sl_idx: int, params: dict,
                           volume: "np.ndarray | None" = None) -> np.ndarray:
        """Slice through ``volume`` (default self.volume) with the same FOV crop /
        oblique sampling as the phantom, so companion volumes (e.g. the fMRI
        activation map) stay pixel-aligned with the rendered phantom slice."""
        vol = self.volume if volume is None else volume
        if self.fov_planning and (abs(self.tilt) > 0.5 or abs(self.rot) > 0.5):
            from oblique import plane_from_angles, oblique_plane
            _, row_vec, col_vec = plane_from_angles(orient, tilt_deg=self.tilt, rot_deg=self.rot)
            cfg = sg.cfg_for(orient)
            center = self._compute_slab_center(orient, sl_idx)
            center[cfg["through_axis"]] = float(sl_idx)
            max_dim = max(vol.shape)
            return oblique_plane(vol, row_vec, col_vec, center,
                                 shape=(max_dim, max_dim), order=0)

        ph = get_slice(vol, orient, sl_idx)
        # Field of view: magnify + wraparound when smaller than the object,
        # shrink + empty surround when larger (sg.fov_transform).
        fov_ratio = float(params.get("FOV", 240.0)) / self.native_fov
        if abs(fov_ratio - 1.0) > 0.01:
            ph = sg.fov_transform(ph, fov_ratio)
        if self.fov_planning and self.inplane_fov_pct < 100:
            ph = sg.fov_crop(orient, ph, self.inplane_fov_pct / 100.0, self.inplane_off)
        return ph

    # --- B0 field -----------------------------------------------------------
    def _b0_volume(self, field_strength_T: float) -> np.ndarray:
        """3D susceptibility B0 field (Hz) for the active volume, cached."""
        vol = self.volume
        key = (vol.shape, int(vol.sum()), round(float(field_strength_T), 3))
        if self._b0_cache is None or self._b0_cache[0] != key:
            field = b0.susceptibility_b0_map(vol, field_strength_T=field_strength_T)
            self._b0_cache = (key, field)
        return self._b0_cache[1]

    def _b0_field_slice(self, orient: str, sl_idx: int, params: dict,
                        field_strength_T: float) -> np.ndarray:
        """2D B0 field slice (Hz) aligned to the (non-oblique) phantom slice."""
        sl = get_slice(self._b0_volume(field_strength_T), orient, sl_idx)
        fov_ratio = float(params.get("FOV", 240.0)) / self.native_fov
        if abs(fov_ratio - 1.0) > 0.01:
            sl = sg.fov_transform(sl, fov_ratio)
        if self.fov_planning and self.inplane_fov_pct < 100:
            sl = sg.fov_crop(orient, sl, self.inplane_fov_pct / 100.0, self.inplane_off)
        return sl

    # --- SNR measurement ----------------------------------------------------
    @staticmethod
    def _resize_nn(arr: np.ndarray, shape) -> np.ndarray:
        """Nearest-neighbor resize of a label map to `shape` (no scipy needed)."""
        if arr.shape == tuple(shape):
            return arr
        ys = np.clip(np.linspace(0, arr.shape[0] - 1, shape[0]).round().astype(int), 0, arr.shape[0] - 1)
        xs = np.clip(np.linspace(0, arr.shape[1] - 1, shape[1]).round().astype(int), 0, arr.shape[1] - 1)
        return arr[np.ix_(ys, xs)]

    def _aligned_labels(self, recon: np.ndarray, phantom_slice: np.ndarray) -> np.ndarray:
        if phantom_slice.shape == recon.shape:
            return phantom_slice
        return self._resize_nn(phantom_slice, recon.shape)

    def _tissue_ref_signal(self, recon: np.ndarray, phantom_slice: np.ndarray) -> float:
        """Mean signal over brain tissue (CSF/GM/WM) used as the SNR reference level."""
        labels = self._aligned_labels(recon, phantom_slice)
        mask = np.isin(labels, (1, 2, 3))
        if np.any(mask):
            val = float(recon[mask].mean())
            if val > 0:
                return val
        bright = recon[recon > 0]
        if bright.size:
            return float(bright.mean())
        mx = float(np.max(recon))
        return mx * 0.5 if mx > 0 else 0.0

    def _measure_snr(self, recon: np.ndarray, phantom_slice: np.ndarray) -> dict:
        """Console-style SNR: tissue-ROI mean / noise sigma from a signal-free region.

        Background noise in a magnitude image is Rayleigh-distributed
        (std = sigma·sqrt(2 − π/2)); divide that out to recover Gaussian sigma.
        """
        RAYLEIGH = np.sqrt(2.0 - np.pi / 2.0)
        labels = self._aligned_labels(recon, phantom_slice)

        bg = recon[labels == 0]
        sigma = None
        if bg.size > 50 and bg.std() > 0:
            sigma = bg.std() / RAYLEIGH
        if sigma is None or sigma <= 0:
            flat = np.sort(recon.ravel())
            low = flat[: max(50, flat.size // 20)]
            sigma = (low.std() / RAYLEIGH) if low.std() > 0 else max(1e-6, float(np.max(recon)) * 1e-3)

        out = {"sigma": float(sigma), "wm": 0.0, "gm": 0.0}
        for name, lab in (("wm", 3), ("gm", 2)):
            roi = recon[labels == lab]
            if roi.size and sigma > 0:
                out[name] = float(roi.mean() / sigma)
        return out

    # --- per-slice rendering ------------------------------------------------
    def _simulate_single_slice(self, params: dict, orient: str, sl_idx: int) -> np.ndarray:
        seq = params["sequence"]; TR = params["TR"]; TE = params["TE"]; TI = params["TI"]; FA = params["flip_angle"]
        if TE >= TR:
            TE = TR - 5
        phantom_slice = self._get_phantom_slice(orient, sl_idx, params)

        # Tissue property pipeline: measured field-strength table (tissue_db) → Gd
        tprops = tissue_db.properties(params.get("field_strength", "3T"))
        gd_active = params.get("contrast_enabled") and params.get("contrast_dose", 0) > 0
        if gd_active:
            tprops = rendering.apply_gd(tprops, params["contrast_dose"] * 0.1)

        # EPI shares the T2*-weighted GRE base; its readout artifacts are applied
        # downstream in simulate().
        seq_map = {"Spin Echo": "SE", "Gradient Echo": "GRE", "Inversion Recovery": "IR",
                   "Echo Planar (EPI)": "GRE", "Balanced SSFP": "bSSFP"}
        if seq in seq_map:
            return rendering.simulate_slice_props(phantom_slice, TR, TE, seq_map[seq], TI, FA, tprops)
        elif seq == "FSE / TSE":
            return simulate_fse_image(phantom_slice, TR, TE, params["etl"], params["echo_spacing"], tprops)
        elif seq == "Diffusion (DWI)":
            direction = {"Left-Right": [1.0, 0.0], "Up-Down": [0.0, 1.0], "Diagonal": [0.707, 0.707]}[params["diff_direction"]]
            if params["diff_display"] == "DWI":
                return simulate_diffusion_3d_slice(phantom_slice, params["b_value"], direction, TR, TE)
            elif params["diff_display"] == "ADC Map":
                return simulate_adc_map_3d(phantom_slice)
            elif params["diff_display"] == "FA Map":
                return simulate_fa_map_3d(phantom_slice)
        elif seq == "MR Angiography":
            # Maneuverable rotating MIP of the 3D TOF volume (azimuth/elevation),
            # the way an angiogram is reviewed — not a fixed slice. During an
            # interactive click-drag rotate, project a 2x-downsampled volume so the
            # MIP stays responsive (~8x faster); full resolution renders on release.
            tof = self._tof_volume(TR, TE, FA)
            if params.get("angio_fast"):
                tof = np.ascontiguousarray(tof[::2, ::2, ::2])
            return angiography.rotating_mip(tof,
                                            params.get("angio_azimuth", 0),
                                            params.get("angio_elevation", 0))
        elif seq == "fMRI (BOLD)":
            # Slice the activation with the SAME FOV crop / oblique geometry as the
            # phantom so the two stay pixel-aligned (else masking raises IndexError).
            act = self._get_phantom_slice(orient, sl_idx, params, volume=self.activation)
            if params["fmri_display"] == "EPI Image":
                return simulate_fmri_3d_slice(phantom_slice, act, TR, TE, FA, True)
            elif params["fmri_display"] == "Activation Map":
                return compute_activation_map_3d(phantom_slice, act, TR, TE, FA)
            elif params["fmri_display"] == "T-statistic Map":
                img = compute_tstat_map_3d(phantom_slice, act, TR, TE, FA, params["fmri_volumes"])
                return np.where(img > params["fmri_threshold"], img, 0)
        elif seq == "Quantitative (qMRI)":
            disp = params["qmri_display"]
            if disp == "T1 Map (VFA)":
                fas = [2.0, 5.0, 10.0, 15.0, 20.0]
                series = qmri.simulate_vfa_series(phantom_slice, fas, TR_ms=15.0, TE_ms=3.0, tissue_props=tprops)
                return qmri.vfa_t1_map(series, fas, 15.0)
            elif disp == "T2 Map (multi-echo)":
                tes = [10.0, 30.0, 50.0, 70.0, 90.0, 110.0]
                series = qmri.simulate_multi_echo_series(phantom_slice, tes, TR_ms=2000.0, sequence="SE", tissue_props=tprops)
                return qmri.multi_echo_t2_map(series, tes)
            elif disp == "T2* Map (multi-echo)":
                tes = [5.0, 10.0, 20.0, 30.0, 40.0, 50.0]
                series = qmri.simulate_multi_echo_series(phantom_slice, tes, TR_ms=500.0, flip_angle_deg=FA, sequence="GRE", tissue_props=tprops)
                return qmri.t2star_map(series, tes)
            elif disp == "Synthetic SE":
                T1m, T2m, PDm = rendering.param_maps(phantom_slice, tprops, ("T1", "T2", "PD"))
                return qmri.synthetic_contrast(T1m, T2m, PDm, TR, TE, sequence="SE")
        return np.zeros((181, 181), dtype=float)

    # --- full acquisition ---------------------------------------------------
    def simulate(self, params: dict) -> tuple[np.ndarray, dict]:
        orient = self.orientation; sl_idx = self.slice_idx
        matrix = params["matrix_size"]; fov_frac = params["fov_fraction"] / 100.0
        thickness = int(params["slice_thickness"]); R = params["accel_factor"]
        max_sl = self.get_max_slice_idx()

        if thickness > 1 and params["sequence"] not in ["MR Angiography"]:
            start = max(0, sl_idx - thickness // 2); end = min(max_sl, sl_idx + thickness // 2)
            slabs = np.stack([self._simulate_single_slice(params, orient, s)
                              for s in range(start, end + 1)])
            # Imperfect RF slice profile: centre-weighted, not a flat average.
            w = _slice_profile_weights(slabs.shape[0])
            image = np.tensordot(w, slabs, axes=(0, 0))
        else:
            image = self._simulate_single_slice(params, orient, sl_idx)

        phantom_slice = self._get_phantom_slice(orient, sl_idx, params)
        is_map = params["sequence"] == "Diffusion (DWI)" and params["diff_display"] in ["ADC Map", "FA Map"]
        is_map = is_map or (params["sequence"] == "fMRI (BOLD)" and params["fmri_display"] in ["Activation Map", "T-statistic Map"])
        is_map = is_map or (params["sequence"] == "Quantitative (qMRI)")
        # MRA renders a 3D-projection MIP, not a slice acquisition — bypass the
        # texture/k-space/noise pipeline and display the projection directly.
        is_map = is_map or (params["sequence"] == "MR Angiography")

        # MR tissue texture: when a real-MRI detail field is available (body
        # regions) modulate the flat per-label signal by it, so organs show real
        # parenchyma / vessels / heterogeneity while keeping label-based TR/TE
        # contrast. Otherwise fall back to deterministic correlated noise.
        if not is_map and phantom_slice.shape == image.shape:
            _tm = phantom_slice > 0
            image = image.astype(float, copy=True)
            tex_slice = None
            if self.texture is not None and self.texture.shape == self.volume.shape:
                ts = self._get_phantom_slice(orient, sl_idx, params, volume=self.texture)
                if ts.shape == image.shape:
                    tex_slice = ts
            if tex_slice is not None:
                image[_tm] = np.maximum(0.0, image[_tm] * tex_slice[_tm])
            else:
                _rng = np.random.default_rng(
                    sl_idx * 7919 + {'axial': 0, 'coronal': 1, 'sagittal': 2}.get(orient, 0))
                _n = gaussian_filter(_rng.standard_normal(image.shape).astype(float), sigma=2.5)
                _n /= max(float(np.abs(_n).max()), 1e-9)
                image[_tm] = np.maximum(0.0, image[_tm] * (1.0 + 0.08 * _n[_tm]))
            # Partial-volume boundary mixing (pv tissue-fraction model)
            image = rendering.partial_volume(image, phantom_slice, params.get("pv_sigma", 10) / 10.0)
            image[~_tm] = 0.0

        if not is_map:
            if params["motion_enabled"]:
                _mseed = (sl_idx * 7919 + {"axial": 0, "coronal": 17, "sagittal": 37}.get(orient, 0)) & 0xFFFFFFFF
                image = add_motion_artifact(image, params["motion_type"],
                                            params["motion_amplitude"], 3,
                                            rng=np.random.default_rng(_mseed))
            if params["chemical_shift_enabled"] and phantom_slice.shape == image.shape:
                _b0_cs = _B0_MAP.get(params.get("field_strength", "3T"), 3.0)
                image = add_chemical_shift_artifact(image, phantom_slice,
                    calculate_chemical_shift_pixels(params["bandwidth"] * 1000 / matrix, field_strength=_b0_cs))
            if params["susceptibility_enabled"] and phantom_slice.shape == image.shape:
                image = add_susceptibility_artifact(image, phantom_slice,
                                                    params["susceptibility_strength"] / 10.0)

            # B1+ transmit inhomogeneity and MT act on the signal image before k-space.
            _field = params.get("field_strength", "3T")
            _B0_val = _B0_MAP.get(_field, 3.0)
            _tprops = tissue_db.properties(_field)
            if params.get("b1_inhom_enabled"):
                image = rendering.apply_b1(image, phantom_slice, _tprops, params["sequence"],
                                           params["flip_angle"], params["TR"], params["TE"], _B0_val)
            if params.get("mt_enabled"):
                image = rendering.apply_mt(image, phantom_slice, _tprops, params.get("mt_power", 0),
                                           params["sequence"], params["TR"], params["TE"], params["flip_angle"])

            # Flowing blood: signal void on the spin-echo family, inflow
            # brightening on gradient echo (static elsewhere).
            if params.get("flow_enabled", True) and phantom_slice.shape == image.shape:
                image = flow.apply_flow(image, phantom_slice, params["sequence"],
                                        _tprops.get(11, {}), params["TE"],
                                        params["flip_angle"],
                                        velocity=params.get("flow_velocity", 70) / 100.0)

            # Balanced SSFP: off-resonance produces the characteristic signal-null
            # bands. Off-resonance = an imperfect-shim linear gradient plus the
            # real susceptibility field; longer TR packs more bands.
            if params["sequence"] == "Balanced SSFP" and phantom_slice.shape == image.shape:
                from signal_engine import ssfp_banding
                H, W = image.shape
                ramp = (np.arange(H)[:, None] / max(H - 1, 1) - 0.5) * 120.0   # ±60 Hz shim
                try:
                    b0f = self._b0_field_slice(orient, sl_idx, params, _B0_val)
                    off = ramp + (b0f if b0f.shape == image.shape else 0.0)
                except Exception:
                    off = ramp
                (T2m,) = rendering.param_maps(phantom_slice, _tprops, ("T2",))
                E2 = np.exp(-params["TR"] / np.maximum(T2m, 1e-6))
                image = image * ssfp_banding(off, params["TR"], E2)

            # Fat-water phase cycling: automatic for GRE (SE refocuses this).
            if params["sequence"] in ("Gradient Echo", "MR Angiography") and phantom_slice.shape == image.shape:
                image = rendering.gre_fatwater_phase(image, phantom_slice, params["TE"], _B0_val)

            # EPI readout artifacts: T2* blur, B0 geometric distortion, N/2 ghost.
            if params["sequence"] == "Echo Planar (EPI)" and phantom_slice.shape == image.shape:
                _t2s = rendering.param_maps(phantom_slice, _tprops, ("T2star",))[0]
                _peak = params.get("epi_b0_hz", 0) * (_B0_val / 3.0)
                try:
                    _b0field = self._b0_field_slice(orient, sl_idx, params, _B0_val)
                    _b0 = (rendering.scale_to_peak(_b0field, _peak)
                           if _b0field.shape == image.shape
                           else rendering.epi_b0_field(image.shape, _peak))
                except Exception:
                    _b0 = rendering.epi_b0_field(image.shape, _peak)
                image = rendering.simulate_epi_slice(
                    image, _t2s, _b0,
                    esp_ms=params.get("epi_esp", 5) / 10.0,
                    ghost_phase=params.get("epi_ghost", 0) / 100.0,
                    correct_ghost=params.get("epi_correct_ghost", False))

            _pf = _PF_MAP.get(params.get("pf_fraction", "Full"), 1.0) if params.get("pf_enabled") else None
            _fw = params.get("kspace_filter_window", "hamming") if params.get("kspace_filter_enabled") else None
            reconstructed, kspace_acquired = simulate_acquisition(image, matrix, fov_frac,
                                                                  filter_window=_fw, pf_fraction=_pf)

            # Acceleration is modelled as a *successful* reconstruction: it keeps
            # full resolution and contrast and makes the scan R× faster — the only
            # image cost is an SNR drop of g·√R (handled in the noise model below).
            # We deliberately do NOT run an under-sampled recon here, which would
            # inject gross aliasing that NEX could never recover.
            method = params.get("accel_method", "SENSE")
            g_factor = _accel_gfactor(R, method)

            # --- Physical noise model (Rician), calibrated so the Noise Level
            # slider equals the tissue-average SNR at the reference protocol.
            res_mm = params["FOV"] / matrix
            vox_vol = res_mm * res_mm * max(1, thickness)
            BW_hz = max(1.0, params["bandwidth"] * 1000.0)
            B0_snr = _B0_MAP.get(params.get("field_strength", "3T"), 3.0)
            # Partial Fourier acquires only `_pf` of the phase-encode lines, so
            # SNR drops ~sqrt(fraction) (fewer samples averaged), mirroring the
            # scan-time reduction below.
            pf_snr = np.sqrt(_pf) if _pf else 1.0
            # Slice cross-talk: contiguous 2-D multi-slice loses signal.
            xtalk = _crosstalk_snr_factor(int(params.get("n_slices", 1)),
                                          params.get("slice_gap", 0.0), thickness)
            eff_snr = (params["snr_level"]
                       * (vox_vol / self.VOX_REF)
                       * np.sqrt(max(1, params["NEX"]))
                       * np.sqrt(self.BW_REF / BW_hz)
                       * pf_snr * xtalk
                       / (g_factor * np.sqrt(R))
                       * (B0_snr / 3.0))
            eff_snr = float(np.clip(eff_snr, 1.0, 1e4))
            tissue_ref = self._tissue_ref_signal(reconstructed, phantom_slice)
            if tissue_ref > 0:
                sigma = rician.noise_sigma_from_snr(tissue_ref, eff_snr)
                sigma_map = sigma
                # Subtle, smooth g-factor structure: parallel-imaging noise is a
                # little higher toward the centre (where coil unfolding is least
                # conditioned), growing with g. Mean-preserving, so the average
                # SNR penalty is unchanged — this is texture, not extra noise.
                if g_factor > 1.01:
                    H, W = reconstructed.shape
                    yy, xx = np.ogrid[:H, :W]
                    rr = np.sqrt(((yy - H / 2) / (H / 2 + 1e-9)) ** 2
                                 + ((xx - W / 2) / (W / 2 + 1e-9)) ** 2)
                    amp = min(0.5, g_factor - 1.0)
                    prof = 1.0 + amp * (0.5 - np.clip(rr, 0.0, 1.0))
                    sigma_map = sigma * (prof / float(prof.mean()))
                reconstructed = rician.add_rician_noise(reconstructed, sigma_map)
                if params.get("rician_bias_correction"):
                    reconstructed = rician.rician_bias_correction(reconstructed, sigma)
            if params["zipper_enabled"]:
                reconstructed = add_zipper_artifact(reconstructed, 0.3, 0.12)
        else:
            kspace_acquired = None
            # Parameter maps are otherwise hard-edged (no texture/noise step). Apply
            # partial-volume boundary mixing so a boundary voxel reports a
            # fraction-weighted blend of its tissues — the real PVE in quantitative
            # maps, and it removes the blocky segmented look. (fMRI statistical maps
            # are left crisp — blurring activation would misrepresent it.)
            pv_map = (params["sequence"] == "Quantitative (qMRI)" or
                      (params["sequence"] == "Diffusion (DWI)"
                       and params["diff_display"] in ("ADC Map", "FA Map")))
            if pv_map and phantom_slice.shape == image.shape:
                reconstructed = rendering.partial_volume(
                    image, phantom_slice, params.get("pv_sigma", 10) / 10.0)
            else:
                reconstructed = image

        # Metrics
        TR, TE, FA = params["TR"], params["TE"], params["flip_angle"]
        FOV, NEX, BW = params["FOV"], params["NEX"], params["bandwidth"] * 1000
        ETL = params["etl"] if params["sequence"] == "FSE / TSE" else 1
        pf_val = _PF_MAP.get(params.get("pf_fraction", "Full"), 1.0) if params.get("pf_enabled") else 1.0
        resolution = FOV / matrix
        scan_time = TR * matrix * NEX / (ETL * R) * pf_val / 1000
        seq_map = {"Spin Echo": "SE", "FSE / TSE": "SE", "Gradient Echo": "GRE", "Inversion Recovery": "IR",
                   "Diffusion (DWI)": "Diffusion", "MR Angiography": "GRE", "fMRI (BOLD)": "EPI",
                   "Echo Planar (EPI)": "EPI", "Balanced SSFP": "GRE"}
        B0_sar = _B0_MAP.get(params.get("field_strength", "3T"), 3.0)
        sar = estimate_sar(FA, TR, sequence=seq_map.get(params["sequence"], "SE"))
        sar_head = sar["head"] * (B0_sar / 3.0) ** 2
        metrics = {"scan_time": scan_time, "resolution": resolution, "snr_wm": 0, "snr_gm": 0,
                   "sar_head": sar_head, "sar_exceeds": sar_head > 3.2,
                   "g_factor": _accel_gfactor(R, params.get("accel_method", "SENSE"))}
        if not is_map:
            snr = self._measure_snr(reconstructed, phantom_slice)
            metrics["snr_wm"] = snr["wm"]
            metrics["snr_gm"] = snr["gm"]
            metrics["noise_sigma"] = snr["sigma"]
            t_min = max(scan_time / 60.0, 1e-6)
            metrics["snr_eff"] = snr["wm"] / np.sqrt(t_min)
        else:
            metrics["snr_eff"] = 0.0
        self.last_kspace = kspace_acquired
        return reconstructed, metrics
