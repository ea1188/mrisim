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
from acceleration import apply_parallel_imaging, apply_compressed_sensing
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
import scan_geometry as sg


# Field-strength label → Tesla (labels match tissue_db.FIELD_STRENGTHS).
_B0_MAP: dict[str, float] = {"1.5T": 1.5, "3T": 3.0}

# Partial-Fourier fractions (string label → actual fraction).
_PF_MAP: dict[str, float] = {
    "Full": 1.0, "7/8": 7.0 / 8.0, "6/8": 6.0 / 8.0, "5/8": 5.0 / 8.0,
}


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
        self.last_kspace: np.ndarray | None = None

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

    def _get_phantom_slice(self, orient: str, sl_idx: int, params: dict) -> np.ndarray:
        """Phantom label slice with FOV crop / oblique sampling applied."""
        if self.fov_planning and (abs(self.tilt) > 0.5 or abs(self.rot) > 0.5):
            from oblique import plane_from_angles, oblique_plane
            _, row_vec, col_vec = plane_from_angles(orient, tilt_deg=self.tilt, rot_deg=self.rot)
            vol = self.volume
            cfg = sg.cfg_for(orient)
            center = self._compute_slab_center(orient, sl_idx)
            center[cfg["through_axis"]] = float(sl_idx)
            max_dim = max(vol.shape)
            return oblique_plane(vol, row_vec, col_vec, center,
                                 shape=(max_dim, max_dim), order=0)

        ph = get_slice(self.volume, orient, sl_idx)
        fov_frac = min(1.0, float(params.get("FOV", 240.0)) / self.native_fov)
        if fov_frac < 0.99:
            ph = sg.fov_crop(orient, ph, fov_frac, 0.0)
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
        fov_frac = min(1.0, float(params.get("FOV", 240.0)) / self.native_fov)
        if fov_frac < 0.99:
            sl = sg.fov_crop(orient, sl, fov_frac, 0.0)
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
                   "Echo Planar (EPI)": "GRE"}
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
            if self.real_tof is not None and params["angio_type"] == "TOF":
                return simulate_tof_with_real_data(self.real_tof, orient, sl_idx, TR, TE, FA, params["angio_mip_slab"])
            return simulate_tof_3d_slice(get_slice(self.vessels, orient, sl_idx), TR, TE, FA)
        elif seq == "fMRI (BOLD)":
            act = get_slice(self.activation, orient, sl_idx)
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
            image = np.mean([self._simulate_single_slice(params, orient, s) for s in range(start, end + 1)], axis=0)
        else:
            image = self._simulate_single_slice(params, orient, sl_idx)

        phantom_slice = self._get_phantom_slice(orient, sl_idx, params)
        is_map = params["sequence"] == "Diffusion (DWI)" and params["diff_display"] in ["ADC Map", "FA Map"]
        is_map = is_map or (params["sequence"] == "fMRI (BOLD)" and params["fmri_display"] in ["Activation Map", "T-statistic Map"])
        is_map = is_map or (params["sequence"] == "Quantitative (qMRI)")

        # MR tissue texture: spatially-correlated multiplicative noise + PV blur.
        # Deterministic per (orient, sl_idx) so parameter knobs don't flicker.
        if not is_map and phantom_slice.shape == image.shape:
            _rng = np.random.default_rng(
                sl_idx * 7919 + {'axial': 0, 'coronal': 1, 'sagittal': 2}.get(orient, 0))
            _n = gaussian_filter(_rng.standard_normal(image.shape).astype(float), sigma=2.5)
            _n /= max(float(np.abs(_n).max()), 1e-9)
            _tm = phantom_slice > 0
            image = image.astype(float, copy=True)
            image[_tm] = np.maximum(0.0, image[_tm] * (1.0 + 0.08 * _n[_tm]))
            image = gaussian_filter(image, sigma=0.7)
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

            if R > 1:
                method = params["accel_method"]
                if method == "CS":
                    reconstructed = apply_compressed_sensing(reconstructed, R)
                else:
                    reconstructed, _ = apply_parallel_imaging(reconstructed, R, method)

            # --- Physical noise model (Rician), calibrated so the Noise Level
            # slider equals the tissue-average SNR at the reference protocol.
            res_mm = params["FOV"] / matrix
            vox_vol = res_mm * res_mm * max(1, thickness)
            BW_hz = max(1.0, params["bandwidth"] * 1000.0)
            B0_snr = _B0_MAP.get(params.get("field_strength", "3T"), 3.0)
            g_factor = rendering.g_factor(R)
            eff_snr = (params["snr_level"]
                       * (vox_vol / self.VOX_REF)
                       * np.sqrt(max(1, params["NEX"]))
                       * np.sqrt(self.BW_REF / BW_hz)
                       / (g_factor * np.sqrt(R))
                       * (B0_snr / 3.0))
            eff_snr = float(np.clip(eff_snr, 1.0, 1e4))
            tissue_ref = self._tissue_ref_signal(reconstructed, phantom_slice)
            if tissue_ref > 0:
                sigma = rician.noise_sigma_from_snr(tissue_ref, eff_snr)
                reconstructed = rician.add_rician_noise(reconstructed, sigma)
                if params.get("rician_bias_correction"):
                    reconstructed = rician.rician_bias_correction(reconstructed, sigma)
            if params["zipper_enabled"]:
                reconstructed = add_zipper_artifact(reconstructed, 0.3, 0.12)
        else:
            kspace_acquired = None
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
                   "Echo Planar (EPI)": "EPI"}
        B0_sar = _B0_MAP.get(params.get("field_strength", "3T"), 3.0)
        sar = estimate_sar(FA, TR, sequence=seq_map.get(params["sequence"], "SE"))
        sar_head = sar["head"] * (B0_sar / 3.0) ** 2
        metrics = {"scan_time": scan_time, "resolution": resolution, "snr_wm": 0, "snr_gm": 0,
                   "sar_head": sar_head, "sar_exceeds": sar_head > 3.2,
                   "g_factor": rendering.g_factor(R)}
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
