"""Metrics-panel formatting and contrast weighting (MetricsMixin)."""
from typing import Any

import numpy as np

import rendering
from simulator import _B0_MAP
from app_theme import C_ACCENT

# Relative SAR weighting per sequence (RF duty cycle), used by the SAR readout.
_SAR_SEQ_FACTORS: dict[str, float] = {
    "Spin Echo": 1.5, "FSE / TSE": 1.5, "Gradient Echo": 0.5,
    "Inversion Recovery": 2.0, "Diffusion (DWI)": 1.5,
    "MR Angiography": 0.5, "fMRI (BOLD)": 0.5, "Echo Planar (EPI)": 0.5,
}


class MetricsMixin:
    # Provided by the host window (MRISimulator); annotation-only.
    metrics_labels: Any
    compare_metrics_label: Any
    orientation: Any
    slice_idx: Any
    slice_thickness: Any
    motion_enabled: Any
    chemical_shift_enabled: Any
    susceptibility_enabled: Any
    zipper_enabled: Any
    _update_header: Any

    def update_compare_metrics(self, ma: dict, mb: dict) -> None:
        up, down = "\u2191", "\u2193"

        def d(a: float, b: float, u: str = "", f: str = ".1f") -> str:
            diff = b - a; pct = (diff / a * 100) if a != 0 else 0
            arrow = up if diff > 0 else down if diff < 0 else "="
            return f"{arrow} {abs(diff):{f}}{u} ({abs(pct):.0f}%)"
        rule = "\u2500\u2500"
        cnr_a = abs(ma["snr_wm"] - ma["snr_gm"]); cnr_b = abs(mb["snr_wm"] - mb["snr_gm"])
        text = f"{rule} A vs B {rule}\nTime: {d(ma['scan_time'], mb['scan_time'], 's')}\n"
        text += f"SNR WM: {d(ma['snr_wm'], mb['snr_wm'])}\nCNR: {d(cnr_a, cnr_b)}\n"
        text += f"Res: {d(ma['resolution'], mb['resolution'], 'mm', '.2f')}\nSAR: A={ma['sar_head']:.1f} B={mb['sar_head']:.1f} W/kg"
        self.compare_metrics_label.config(text=text, fg="#ffcc00")

    def update_metrics(self, params: dict, metrics: dict) -> None:
        orient = self.orientation.get(); sl_idx = self.slice_idx.get()
        matrix = params["matrix_size"]
        thickness = int(params.get("slice_thickness", self.slice_thickness.get()))
        R = params["accel_factor"]; ETL = params["etl"] if params["sequence"] == "FSE / TSE" else 1
        pf_on = params.get("pf_enabled", False)
        pf_label = params.get("pf_fraction", "Full") if pf_on else ""
        resolution = metrics["resolution"]

        self.metrics_labels["resolution"].config(text=f"{resolution:.2f} mm")
        self.metrics_labels["voxel_size"].config(text=f"{resolution:.2f}x{resolution:.2f}x{thickness}mm")
        self.metrics_labels["matrix_display"].config(text=f"{matrix}x{matrix}")
        self.metrics_labels["slice_info"].config(text=f"{orient.capitalize()} #{sl_idx}")

        # Scan time with per-factor breakdown
        st = metrics["scan_time"]
        parts = [p for p in [
            f"\u00f7ETL{ETL}" if ETL > 1 else "",
            f"\u00f7R{R}" if R > 1 else "",
            f"\u00d7PF{pf_label}" if pf_on and pf_label != "Full" else "",
        ] if p]
        st_text = f"{int(st // 60)}:{int(st % 60):02d}"
        if parts:
            st_text += "  [" + " ".join(parts) + "]"
        self.metrics_labels["scan_time"].config(text=st_text)

        self.metrics_labels["bw_pixel"].config(text=f"{params['bandwidth'] * 1000 / matrix:.1f}")
        self.metrics_labels["snr_wm"].config(text=f"{metrics['snr_wm']:.1f}")
        self.metrics_labels["snr_gm"].config(text=f"{metrics['snr_gm']:.1f}")
        self.metrics_labels["cnr"].config(text=f"{abs(metrics['snr_wm'] - metrics['snr_gm']):.1f}")
        self.metrics_labels["snr_eff"].config(text=f"{metrics.get('snr_eff', 0):.1f}")

        # SAR: show max safe FA when limit exceeded
        if metrics["sar_exceeds"]:
            sf = _SAR_SEQ_FACTORS.get(params["sequence"], 1.0)
            fa_max = int(np.clip(90 * np.sqrt(3.2 * max(params["TR"], 10) / (2500.0 * sf)), 1, 90))
            sar_text = f"{metrics['sar_head']:.1f} W/kg  \u26a0\ufe0f (safe \u2264{fa_max}\u00b0)"
        else:
            sar_text = f"{metrics['sar_head']:.1f} W/kg"
        self.metrics_labels["sar"].config(text=sar_text, fg="#ff6b6b" if metrics["sar_exceeds"] else C_ACCENT)

        self.metrics_labels["weighting"].config(
            text=self.determine_weighting(params["TR"], params["TE"], params["sequence"]))
        self.metrics_labels["field_disp"].config(text=params.get("field_strength", "3T"))

        # Fat-water phase (GRE only; SE refocuses chemical-shift phase)
        _B0_fw = _B0_MAP.get(params.get("field_strength", "3T"), 3.0)
        if params["sequence"] in ("Gradient Echo", "MR Angiography"):
            fw_lbl = rendering.gre_fw_phase_label(params["TE"], _B0_fw)
            fw_col = "#69db7c" if fw_lbl == "In-phase" else ("#ff6b6b" if fw_lbl == "Opposed" else "#ffcc00")
            self.metrics_labels["fw_phase"].config(text=fw_lbl, fg=fw_col)
        else:
            self.metrics_labels["fw_phase"].config(text="N/A (SE)", fg="#586273")

        # ETL / Accel / PF summary line (R shown with its real SENSE g-factor)
        tokens = [t for t in [
            f"ETL={ETL}" if ETL > 1 else "",
            f"R={R} (g={metrics.get('g_factor', 1.0):.2f})" if R > 1 else "",
            f"PF={pf_label}" if pf_on else "",
        ] if t]
        self.metrics_labels["etl_accel"].config(text=" ".join(tokens) or "None")

        # Active effects list
        active = []
        if params.get("motion_enabled", self.motion_enabled.get()): active.append("Motion")
        if params.get("chemical_shift_enabled", self.chemical_shift_enabled.get()): active.append("ChemShift")
        if params.get("susceptibility_enabled", self.susceptibility_enabled.get()): active.append("Suscept.")
        if params.get("zipper_enabled", self.zipper_enabled.get()): active.append("Zipper")
        if params.get("contrast_enabled"): active.append(f"Gd×{params.get('contrast_dose',1)*0.1:.1f}mmol/kg")
        if params["fov_fraction"] < 100: active.append("Aliasing")
        if pf_on: active.append(f"PF({pf_label})")
        if params.get("kspace_filter_enabled"): active.append(f"Filter({params.get('kspace_filter_window','')})")
        if matrix < 128: active.append("Blur")
        if metrics["sar_exceeds"]: active.append("SAR!")
        self.metrics_labels["artifacts"].config(
            text=", ".join(active) if active else "None",
            fg="#ff6b6b" if active else C_ACCENT)

        self._update_header()

    def determine_weighting(self, TR: float, TE: float, seq: str) -> str:
        if seq == "Diffusion (DWI)": return "Diffusion"
        if seq == "MR Angiography": return "Flow"
        if seq == "fMRI (BOLD)": return "T2* (BOLD)"
        if seq == "Quantitative (qMRI)": return "Quantitative"
        if seq == "Echo Planar (EPI)": return "T2* (EPI)"
        if seq == "Balanced SSFP": return "T2/T1 (bSSFP)"
        if TR < 800 and TE < 30: return "T1-weighted"
        elif TR > 2000 and TE > 60: return "T2-weighted"
        elif TR > 2000 and TE < 30: return "PD-weighted"
        return "Mixed"

