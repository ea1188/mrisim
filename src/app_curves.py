"""Signal-vs-parameter curve rendering for the side panel (CurvesMixin).

Split out of app_qt; mixed into MRISimulator. All physics routes through the
tested signal_engine equations so the curve tracks the rendered image.
"""
from dataclasses import dataclass
from typing import Any

import numpy as np

import tissue_db
from signal_engine import (spin_echo_signal, gradient_echo_signal,
                           inversion_recovery_signal, balanced_ssfp_signal)
from fse import compute_fse_echo_train
from phantom3d_extended import get_diffusion_properties_3d
import perfusion
import dsc_dce
from theme_colors import C_CHIP, C_BORDER, C_TEXT, C_HEADER, C_TEXT_DIM, C_ACCENT

# Tissue name → tissue_db label, for the curve builders.
_NAME2LABEL = {"white_matter": 3, "gray_matter": 2, "csf": 1, "fat": 4, "muscle": 6}
_LEGEND = dict(fontsize=8, facecolor=C_CHIP, edgecolor=C_BORDER, labelcolor=C_TEXT, framealpha=0.95)


@dataclass(frozen=True)
class _CurveCtx:
    """The inputs a single curve builder needs — assembled once in `_plot_curves`."""
    ax: Any
    params: dict
    seq: str
    TR: float
    TE: float
    TI: float
    FA: float
    tissues: dict


class CurvesMixin:
    # Provided by the host window (MRISimulator); declared for the type checker.
    axes: Any
    plot_curve_mode: Any
    current_image: Any

    @staticmethod
    def _curve_signal(seq: str, props: dict, TR: Any, TE: Any, TI: Any, FA: Any) -> Any:
        """Per-tissue signal from the *same* tested library equations the image
        uses, so the plotted curve provably tracks the picture. TR/TE may be
        scalars or numpy arrays (the swept axis). GRE/EPI use the measured T2*
        (not an inline T2 approximation); bSSFP/EPI no longer fall through to IR."""
        T1, T2, PD = props["T1"], props["T2"], props["PD"]
        T2star = props.get("T2star", T2)
        if seq in ("Gradient Echo", "Echo Planar (EPI)", "Susceptibility (SWI)"):
            return gradient_echo_signal(T1, T2star, PD, TR, TE, FA)
        if seq == "Balanced SSFP":
            return balanced_ssfp_signal(T1, T2, PD, TR, TE, FA)
        if seq == "Inversion Recovery":
            return inversion_recovery_signal(T1, T2, PD, TR, TE, TI)
        return spin_echo_signal(T1, T2, PD, TR, TE)   # SE / FSE / qMRI / default

    def _plot_curves(self, params: dict) -> None:
        seq = params["sequence"]
        mode = self.plot_curve_mode.get()
        tdb = tissue_db.properties(params.get("field_strength", "3T"))
        c = _CurveCtx(self.axes[1], params, seq, params["TR"], params["TE"], params["TI"],
                      params["flip_angle"], {name: tdb[lab] for name, lab in _NAME2LABEL.items()})

        # A few sequences own a fixed curve type (ignore the mode toggle); the rest
        # (SE / GRE / IR …) dispatch on the curve-mode toggle, defaulting to TE decay.
        # Register a curve by adding one entry here + a `_curve_*` builder.
        seq_builder = {
            "FSE / TSE": self._curve_fse,
            "Diffusion (DWI)": self._curve_diffusion,
            "MR Angiography": self._curve_mra,
            "fMRI (BOLD)": self._curve_fmri,
            "Perfusion (Dynamic)": self._curve_perfusion_dynamic,
            "Perfusion (ASL)": self._curve_perfusion_asl,
        }.get(seq)
        mode_builder = {
            "TR recovery": self._curve_tr_recovery,
            "TI sweep": self._curve_ti_sweep,
            "Flip angle": self._curve_flip_angle,
            "Contrast Map": self._curve_contrast_map,
            "Histogram": self._curve_histogram,
        }.get(mode)
        (seq_builder or mode_builder or self._curve_te_decay)(c)

        ax = self.axes[1]
        ax.set_facecolor(C_HEADER)
        ax.tick_params(colors=C_TEXT_DIM, labelsize=8, length=3)
        for _s in ax.spines.values():
            _s.set_color(C_BORDER)
        ax.grid(True, color="#202830", linewidth=0.6, alpha=0.9)
        ax.set_axisbelow(True)

    # --- sequence-specific builders (ignore the curve-mode toggle) -------------
    def _curve_fse(self, c: "_CurveCtx") -> None:
        ax = c.ax
        for tn, color, T1, T2, PD in [("WM", '#ff6b6b', 830, 80, 0.65),
                                       ("GM", '#69db7c', 1330, 100, 0.8),
                                       ("CSF", '#74c0fc', 4500, 2200, 1.0)]:
            te_vals, sigs = compute_fse_echo_train(T1, T2, PD, c.TR, c.params["etl"], c.params["echo_spacing"])
            ax.plot(te_vals, sigs, color=color, linewidth=2, label=tn, marker='o', markersize=3)
        ax.axvline(x=c.TE, color='yellow', linestyle='--', alpha=0.7, label=f'TE_eff={c.TE:.0f}')
        ax.set_xlabel('Echo Time (ms)', color='white')
        ax.set_title('FSE Echo Train Decay', color='white', fontsize=11)

    def _curve_diffusion(self, c: "_CurveCtx") -> None:
        ax = c.ax
        b_range = np.arange(0, 3001, 50); dp = get_diffusion_properties_3d(None)
        for name, color, label in [("WM", '#ff6b6b', 3), ("GM", '#69db7c', 2), ("CSF", '#74c0fc', 1)]:
            props = c.tissues[name.lower().replace("wm", "white_matter").replace("gm", "gray_matter")]
            S0 = spin_echo_signal(props["T1"], props["T2"], props["PD"], c.TR, c.TE)
            ax.plot(b_range, S0 * np.exp(-b_range * dp[label]["ADC"] * 1e-3), color=color, linewidth=2, label=name)
        ax.axvline(x=c.params["b_value"], color='yellow', linestyle='--', alpha=0.7)
        ax.set_xlabel('b-value (s/mm²)', color='white')
        ax.set_title('Signal vs b-value', color='white', fontsize=11)

    def _curve_mra(self, c: "_CurveCtx") -> None:
        ax = c.ax
        fa_range = np.arange(1, 91, 1)
        for name, color, T1, PD in [("Brain", '#69db7c', 1330, 0.8), ("Blood", '#ff6b6b', 1930, 0.9)]:
            if "Blood" in name:
                ax.plot(fa_range, PD * np.sin(np.radians(fa_range)) * np.exp(-c.TE / 50),
                        color=color, linewidth=2, label=name)
            else:
                ax.plot(fa_range, [gradient_echo_signal(T1, 50, PD, c.TR, c.TE, float(fa)) for fa in fa_range],
                        color=color, linewidth=2, label=name)
        ax.axvline(x=c.FA, color='yellow', linestyle='--', alpha=0.7, label=f'FA={c.FA:.0f}°')
        # Ernst angle for brain tissue
        ernst_brain = float(np.degrees(np.arccos(np.exp(-c.TR / 1330))))
        ax.axvline(x=ernst_brain, color='#9aa4b2', linestyle=':', alpha=0.6, label=f'Ernst={ernst_brain:.0f}°')
        ax.set_xlabel('Flip Angle (°)', color='white')
        ax.set_title('TOF Signal vs Flip Angle', color='white', fontsize=11)

    def _curve_fmri(self, c: "_CurveCtx") -> None:
        ax = c.ax
        te_range = np.arange(5, 100, 1, dtype=float)
        bs = te_range * np.exp(-te_range / 60); bs /= bs.max()
        ax.plot(te_range, bs, color='#ff6b6b', linewidth=2, label='BOLD sensitivity')
        ax.plot(te_range, np.exp(-te_range / 60), color='#69db7c', linewidth=2, label='GRE signal')
        ax.axvline(x=c.TE, color='yellow', linestyle='--', alpha=0.7, label=f'TE={c.TE:.0f}')
        ax.set_xlabel('TE (ms)', color='white')
        ax.set_title('BOLD Sensitivity vs TE', color='white', fontsize=11)

    def _curve_perfusion_dynamic(self, c: "_CurveCtx") -> None:
        ax = c.ax
        if "Ktrans" in c.params.get("perf_dyn_display", "CBV (DSC)"):
            # DCE Tofts uptake: behind an intact blood–brain barrier the curve stays
            # ~flat (Ktrans≈0); leaky tumour vasculature enhances over the acquisition.
            t = np.linspace(0.0, 6.0, 240)            # minutes
            for name, color, lab in [("Grey matter", '#69db7c', 2), ("White matter", '#ff6b6b', 3), ("Tumour", '#ffd43b', 26)]:
                ax.plot(t, dsc_dce.tofts_curve(t, dsc_dce.KTRANS_PERMIN[lab]), color=color, linewidth=2, label=name)
            ax.set_xlabel('Time (min)', color='white')
            ax.set_title('DCE uptake (Tofts) — Ktrans permeability', color='white', fontsize=11)
        else:
            # DSC first-pass bolus C(t) ∝ ΔR2*: peak height tracks CBF and width tracks
            # MTT, so the area tracks CBV. A stroke core is low + delayed (long MTT);
            # a tumour is high (raised CBV).
            t = np.linspace(0.0, 60.0, 240)           # seconds
            for name, color, lab in [("Grey matter", '#69db7c', 2), ("Infarct", '#74c0fc', 24), ("Tumour", '#ffd43b', 26)]:
                cbf, cbv = perfusion.CBF_ML100G[lab], dsc_dce.CBV_ML100G[lab]
                mtt = 60.0 * cbv / cbf                # central volume theorem (s)
                cv = dsc_dce.gamma_variate(t, t0=8.0, alpha=3.0, beta=mtt / 3.0, amp=1.0)
                cv = cv / (float(np.max(cv)) or 1.0) * (cbf / 60.0)   # peak height ∝ CBF (grey ≈ 1)
                ax.plot(t, cv, color=color, linewidth=2, label=name)
            ax.set_xlabel('Time (s)', color='white')
            ax.set_title('DSC first-pass bolus — area ∝ CBV, width ∝ MTT', color='white', fontsize=11)
        ax.legend(**_LEGEND)

    def _curve_perfusion_asl(self, c: "_CurveCtx") -> None:
        # The labelled blood signal decays with the post-label delay (blood T1), and
        # grey-matter flow exceeds white; the marker shows the prescribed PLD.
        ax = c.ax
        pld = np.linspace(0.0, 4000.0, 200)           # ms
        for name, color, lab in [("Grey matter", '#69db7c', 2), ("White matter", '#ff6b6b', 3)]:
            frac = perfusion.asl_delta_fraction(np.full_like(pld, perfusion.CBF_ML100G[lab]), pld, 1800.0, 1650.0)
            ax.plot(pld, np.asarray(frac) * 100.0, color=color, linewidth=2, label=name)
        cur_pld = float(c.params.get("pld", 1800.0))
        ax.axvline(x=cur_pld, color='yellow', linestyle='--', alpha=0.7, label=f'PLD={cur_pld:.0f}')
        ax.set_xlabel('Post-label delay (ms)', color='white')
        ax.set_title('ASL signal ΔM vs PLD (% of M0)', color='white', fontsize=11)
        ax.legend(**_LEGEND)

    # --- curve-mode builders (SE / GRE / IR) -----------------------------------
    def _curve_tr_recovery(self, c: "_CurveCtx") -> None:
        ax = c.ax
        tr_range = np.arange(100, 8001, 50, dtype=float)
        for tlabel, color, key in [("White Matter", '#ff6b6b', "white_matter"),
                                   ("Gray Matter", '#69db7c', "gray_matter"),
                                   ("CSF", '#74c0fc', "csf")]:
            sig = self._curve_signal(c.seq, c.tissues[key], tr_range, c.TE, c.TI, c.FA)
            ax.plot(tr_range, sig, color=color, linewidth=2, label=tlabel)
        ax.axvline(x=c.TR, color='yellow', linestyle='--', alpha=0.7, label=f'TR={c.TR:.0f}')
        ax.set_xlabel('TR (ms)', color='white')
        ax.set_ylabel('Signal (a.u.)', color='white')
        ax.set_title('T1 Recovery  (signal vs TR)', color='white', fontsize=11)
        ax.legend(**_LEGEND)

    def _curve_ti_sweep(self, c: "_CurveCtx") -> None:
        # Signal vs TI — most useful for IR/STIR/FLAIR education
        ax = c.ax
        ti_max = min(max(c.TR * 0.99, 500), 5000)
        ti_range = np.arange(50, ti_max, 10, dtype=float)
        for tlabel, color, key in [("White Matter", '#ff6b6b', "white_matter"),
                                   ("Gray Matter", '#69db7c', "gray_matter"),
                                   ("CSF", '#74c0fc', "csf"),
                                   ("Fat", '#ffd43b', "fat")]:
            if key not in c.tissues:
                continue
            props = c.tissues[key]
            signed = props["PD"] * (1 - 2 * np.exp(-ti_range / props["T1"]) + np.exp(-c.TR / props["T1"])) * np.exp(-c.TE / props["T2"])
            mag = np.abs(signed)
            ax.plot(ti_range, signed, color=color, linewidth=1, linestyle='--', alpha=0.35)
            ax.plot(ti_range, mag, color=color, linewidth=2, label=tlabel)
            # Null point
            denom_null = 1 + np.exp(-c.TR / props["T1"])
            if denom_null > 1e-9:
                null_ti = props["T1"] * np.log(2.0 / denom_null)
                if 50 < null_ti < ti_max:
                    ax.axvline(x=null_ti, color=color, linestyle=':', alpha=0.55, linewidth=1)
                    ax.text(null_ti + ti_max * 0.01, ax.get_ylim()[1] * 0.02 if ax.get_ylim()[1] > 0 else 0.01,
                            f"null\n{null_ti:.0f}ms", color=color, fontsize=7, va='bottom')
        ax.axhline(y=0, color='#3a424d', linewidth=0.8, alpha=0.5)
        ax.axvline(x=c.TI, color='yellow', linestyle='--', alpha=0.8, label=f'TI={c.TI:.0f}')
        ax.set_xlabel('TI (ms)', color='white')
        ax.set_ylabel('Signal (a.u.)', color='white')
        ax.set_title('IR Signal vs TI  (— magnitude · - - signed)', color='white', fontsize=10)
        ax.legend(**_LEGEND)

    def _curve_flip_angle(self, c: "_CurveCtx") -> None:
        # Signal vs flip angle — the Ernst-angle teaching curve. Most meaningful
        # for spoiled gradient-echo (SE is flip-independent → a flat line, which
        # is itself instructive). cos(α_Ernst) = exp(-TR/T1).
        ax = c.ax
        fa_sweep = np.arange(1.0, 91.0)
        for tlabel, color, key in [("White Matter", '#ff6b6b', "white_matter"),
                                   ("Gray Matter", '#69db7c', "gray_matter"),
                                   ("CSF", '#74c0fc', "csf")]:
            props = c.tissues[key]
            # Broadcast to the swept axis: flip-independent sequences (SE/IR)
            # return a scalar → a flat line, which itself shows they don't vary
            # with flip (only gradient-echo has an Ernst peak).
            sig = np.broadcast_to(
                np.asarray(self._curve_signal(c.seq, props, c.TR, c.TE, c.TI, fa_sweep), dtype=float),
                fa_sweep.shape)
            ax.plot(fa_sweep, sig, color=color, linewidth=2, label=tlabel)
            e1 = float(np.exp(-c.TR / props["T1"]))
            a_ernst = float(np.degrees(np.arccos(np.clip(e1, -1.0, 1.0))))
            if 1.0 < a_ernst < 90.0:
                ax.axvline(x=a_ernst, color=color, linestyle=':', alpha=0.6, linewidth=1)
                ax.text(a_ernst, 0.93, f"{a_ernst:.0f}°", transform=ax.get_xaxis_transform(),
                        color=color, fontsize=7, ha='center', va='top')
        ax.axvline(x=c.FA, color='yellow', linestyle='--', alpha=0.8, label=f'flip={c.FA:.0f}°')
        ax.set_xlabel('Flip angle (°)', color='white')
        ax.set_ylabel('Signal (a.u.)', color='white')
        _gre_like = ("Gradient Echo", "Balanced SSFP", "Echo Planar (EPI)", "Susceptibility (SWI)")
        _t = 'Signal vs Flip Angle  (· = Ernst angle)' if c.seq in _gre_like \
            else 'Signal vs Flip Angle  (Ernst applies to gradient-echo)'
        ax.set_title(_t, color='white', fontsize=10)
        ax.legend(**_LEGEND)

    def _curve_contrast_map(self, c: "_CurveCtx") -> None:
        # 2-D WM–GM CNR heat map vs TR and TE for the current sequence
        ax = c.ax
        tr_vals = np.logspace(np.log10(200), np.log10(6000), 80)
        te_vals = np.linspace(5, 200, 60)
        TR_g, TE_g = np.meshgrid(tr_vals, te_vals)
        wm = c.tissues["white_matter"]; gm = c.tissues["gray_matter"]
        s_wm = self._curve_signal(c.seq, wm, TR_g, TE_g, c.TI, c.FA)
        s_gm = self._curve_signal(c.seq, gm, TR_g, TE_g, c.TI, c.FA)
        cnr_map = np.abs(s_wm - s_gm)
        ax.imshow(cnr_map, origin='lower', aspect='auto', cmap='hot',
                  extent=[np.log10(200), np.log10(6000), 5, 200], vmin=0)
        ax.plot([np.log10(c.TR)], [c.TE], 'c+', markersize=12, markeredgewidth=2, label=f'TR={c.TR:.0f} TE={c.TE:.0f}')
        tick_trs = [200, 500, 1000, 2000, 4000]
        ax.set_xticks([np.log10(v) for v in tick_trs])
        ax.set_xticklabels([str(v) for v in tick_trs])
        ax.set_xlabel('TR (ms, log scale)', color='white')
        ax.set_ylabel('TE (ms)', color='white')
        ax.set_title('WM–GM CNR map  (brighter = better contrast)', color='white', fontsize=10)
        ax.legend(**_LEGEND)

    def _curve_histogram(self, c: "_CurveCtx") -> None:
        ax = c.ax
        img = self.current_image
        if img is None or img.size == 0:
            ax.text(0.5, 0.5, 'Run simulation first', ha='center', va='center',
                    transform=ax.transAxes, color='white')
            return
        img_pos = img.ravel()
        img_pos = img_pos[img_pos > 0]
        if img_pos.size == 0:
            ax.text(0.5, 0.5, 'No image data', ha='center', va='center',
                    transform=ax.transAxes, color='white')
            return
        ax.hist(img_pos, bins=80, color=C_ACCENT, alpha=0.7, density=True)
        # Annotate tissue ROI means using the tissue table
        for tlabel, color, key in [("WM", '#ff6b6b', "white_matter"),
                                   ("GM", '#69db7c', "gray_matter"),
                                   ("CSF", '#74c0fc', "csf")]:
            mean_sig = float(self._curve_signal(c.seq, c.tissues[key], c.TR, c.TE, c.TI, c.FA))
            ax.axvline(x=mean_sig, color=color, linestyle='--', linewidth=1.5, alpha=0.85,
                       label=f'{tlabel}≈{mean_sig:.3f}')
        ax.set_xlabel('Pixel Value', color='white')
        ax.set_ylabel('Density', color='white')
        ax.set_title('Image Histogram  (dashed = tissue signal prediction)', color='white', fontsize=10)
        ax.legend(**_LEGEND)

    def _curve_te_decay(self, c: "_CurveCtx") -> None:   # the default curve mode
        ax = c.ax
        te_range = np.arange(5, min(300, c.TR), 2)
        for tlabel, color, key in [("White Matter", '#ff6b6b', "white_matter"),
                                   ("Gray Matter", '#69db7c', "gray_matter"),
                                   ("CSF", '#74c0fc', "csf")]:
            sig = self._curve_signal(c.seq, c.tissues[key], c.TR, te_range, c.TI, c.FA)
            ax.plot(te_range, sig, color=color, linewidth=2, label=tlabel)
        ax.axvline(x=c.TE, color='yellow', linestyle='--', alpha=0.7, label=f'TE={c.TE:.0f}')
        if c.seq == "Gradient Echo":
            ernst_gm = float(np.degrees(np.arccos(np.clip(np.exp(-c.TR / 1330), -1.0, 1.0))))
            ax.set_title(f'GRE T2* Decay  (Ernst≈{ernst_gm:.0f}° for GM at this TR)', color='white', fontsize=10)
        elif c.seq == "Inversion Recovery":
            ax.set_title(f'IR T2 Decay at TI={c.TI:.0f}ms  (use TI sweep for null points)', color='white', fontsize=10)
        elif c.seq == "Balanced SSFP":
            ax.set_title('bSSFP Signal vs TE  (T2/T1 — bright fluid)', color='white', fontsize=10)
        elif c.seq == "Echo Planar (EPI)":
            ax.set_title('EPI T2* Decay  (signal vs TE)', color='white', fontsize=10)
        else:
            ax.set_title('T2 Decay  (signal vs TE)', color='white', fontsize=11)
        ax.set_xlabel('TE (ms)', color='white')
        ax.set_ylabel('Signal (a.u.)', color='white')
        ax.legend(**_LEGEND)
