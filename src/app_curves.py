"""Signal-vs-parameter curve rendering for the side panel (CurvesMixin).

Split out of app_qt; mixed into MRISimulator. All physics routes through the
tested signal_engine equations so the curve tracks the rendered image.
"""
from typing import Any

import numpy as np

import tissue_db
from signal_engine import (spin_echo_signal, gradient_echo_signal,
                           inversion_recovery_signal, balanced_ssfp_signal)
from fse import compute_fse_echo_train
from phantom3d_extended import get_diffusion_properties_3d
from theme_colors import C_CHIP, C_BORDER, C_TEXT, C_HEADER, C_TEXT_DIM, C_ACCENT


class CurvesMixin:
    # Provided by the host window (MRISimulator); declared for the type checker.
    axes: Any
    plot_curve_mode: Any
    current_image: Any

    @staticmethod
    def _curve_signal(seq: str, props: dict, TR: Any, TE: Any, TI: float, FA: float) -> Any:
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
        seq, TR, TE, TI, FA = params["sequence"], params["TR"], params["TE"], params["TI"], params["flip_angle"]
        ax = self.axes[1]
        mode = self.plot_curve_mode.get()

        # Tissue curves read from the measured field-strength table (tissue_db),
        # keyed by the names this method uses.
        _tdb = tissue_db.properties(params.get("field_strength", "3T"))
        _NAME2LABEL = {"white_matter": 3, "gray_matter": 2, "csf": 1, "fat": 4, "muscle": 6}
        TISSUES_B0 = {name: _tdb[lab] for name, lab in _NAME2LABEL.items()}

        # --- Sequences with fixed curve type (ignore mode toggle) ----------
        if seq == "FSE / TSE":
            for tn, color, T1, T2, PD in [("WM", '#ff6b6b', 830, 80, 0.65),
                                           ("GM", '#69db7c', 1330, 100, 0.8),
                                           ("CSF", '#74c0fc', 4500, 2200, 1.0)]:
                te_vals, sigs = compute_fse_echo_train(T1, T2, PD, TR, params["etl"], params["echo_spacing"])
                ax.plot(te_vals, sigs, color=color, linewidth=2, label=tn, marker='o', markersize=3)
            ax.axvline(x=TE, color='yellow', linestyle='--', alpha=0.7, label=f'TE_eff={TE:.0f}')
            ax.set_xlabel('Echo Time (ms)', color='white')
            ax.set_title('FSE Echo Train Decay', color='white', fontsize=11)

        elif seq == "Diffusion (DWI)":
            b_range = np.arange(0, 3001, 50); dp = get_diffusion_properties_3d(None)
            for name, color, label in [("WM", '#ff6b6b', 3), ("GM", '#69db7c', 2), ("CSF", '#74c0fc', 1)]:
                props = TISSUES_B0[name.lower().replace("wm", "white_matter").replace("gm", "gray_matter")]
                S0 = spin_echo_signal(props["T1"], props["T2"], props["PD"], TR, TE)
                ax.plot(b_range, S0 * np.exp(-b_range * dp[label]["ADC"] * 1e-3), color=color, linewidth=2, label=name)
            ax.axvline(x=params["b_value"], color='yellow', linestyle='--', alpha=0.7)
            ax.set_xlabel('b-value (s/mm²)', color='white')
            ax.set_title('Signal vs b-value', color='white', fontsize=11)

        elif seq == "MR Angiography":
            fa_range = np.arange(1, 91, 1)
            for name, color, T1, PD in [("Brain", '#69db7c', 1330, 0.8), ("Blood", '#ff6b6b', 1930, 0.9)]:
                if "Blood" in name:
                    ax.plot(fa_range, PD * np.sin(np.radians(fa_range)) * np.exp(-TE / 50),
                            color=color, linewidth=2, label=name)
                else:
                    ax.plot(fa_range, [gradient_echo_signal(T1, 50, PD, TR, TE, float(fa)) for fa in fa_range],
                            color=color, linewidth=2, label=name)
            ax.axvline(x=FA, color='yellow', linestyle='--', alpha=0.7, label=f'FA={FA:.0f}°')
            # Ernst angle for brain tissue
            ernst_brain = float(np.degrees(np.arccos(np.exp(-TR / 1330))))
            ax.axvline(x=ernst_brain, color='#9aa4b2', linestyle=':', alpha=0.6, label=f'Ernst={ernst_brain:.0f}°')
            ax.set_xlabel('Flip Angle (°)', color='white')
            ax.set_title('TOF Signal vs Flip Angle', color='white', fontsize=11)

        elif seq == "fMRI (BOLD)":
            te_range = np.arange(5, 100, 1, dtype=float)
            bs = te_range * np.exp(-te_range / 60); bs /= bs.max()
            ax.plot(te_range, bs, color='#ff6b6b', linewidth=2, label='BOLD sensitivity')
            ax.plot(te_range, np.exp(-te_range / 60), color='#69db7c', linewidth=2, label='GRE signal')
            ax.axvline(x=TE, color='yellow', linestyle='--', alpha=0.7, label=f'TE={TE:.0f}')
            ax.set_xlabel('TE (ms)', color='white')
            ax.set_title('BOLD Sensitivity vs TE', color='white', fontsize=11)

        # --- SE / GRE / IR with mode toggle --------------------------------
        elif mode == "TR recovery":
            tr_range = np.arange(100, 8001, 50, dtype=float)
            _tissue_rows = [("White Matter", '#ff6b6b', "white_matter"),
                            ("Gray Matter",  '#69db7c', "gray_matter"),
                            ("CSF",          '#74c0fc', "csf")]
            for tlabel, color, key in _tissue_rows:
                props = TISSUES_B0[key]
                sig = self._curve_signal(seq, props, tr_range, TE, TI, FA)
                ax.plot(tr_range, sig, color=color, linewidth=2, label=tlabel)
            ax.axvline(x=TR, color='yellow', linestyle='--', alpha=0.7, label=f'TR={TR:.0f}')
            ax.set_xlabel('TR (ms)', color='white')
            ax.set_ylabel('Signal (a.u.)', color='white')
            ax.set_title('T1 Recovery  (signal vs TR)', color='white', fontsize=11)
            ax.legend(fontsize=8, facecolor=C_CHIP, edgecolor=C_BORDER, labelcolor=C_TEXT, framealpha=0.95)

        elif mode == "TI sweep":
            # Signal vs TI — most useful for IR/STIR/FLAIR education
            ti_max = min(max(TR * 0.99, 500), 5000)
            ti_range = np.arange(50, ti_max, 10, dtype=float)
            _ir_tissues = [("White Matter", '#ff6b6b', "white_matter"),
                           ("Gray Matter",  '#69db7c', "gray_matter"),
                           ("CSF",          '#74c0fc', "csf"),
                           ("Fat",          '#ffd43b', "fat")]
            for tlabel, color, key in _ir_tissues:
                if key not in TISSUES_B0:
                    continue
                props = TISSUES_B0[key]
                signed = props["PD"] * (1 - 2 * np.exp(-ti_range / props["T1"]) + np.exp(-TR / props["T1"])) * np.exp(-TE / props["T2"])
                mag = np.abs(signed)
                ax.plot(ti_range, signed, color=color, linewidth=1, linestyle='--', alpha=0.35)
                ax.plot(ti_range, mag, color=color, linewidth=2, label=tlabel)
                # Null point
                denom_null = 1 + np.exp(-TR / props["T1"])
                if denom_null > 1e-9:
                    null_ti = props["T1"] * np.log(2.0 / denom_null)
                    if 50 < null_ti < ti_max:
                        ax.axvline(x=null_ti, color=color, linestyle=':', alpha=0.55, linewidth=1)
                        ax.text(null_ti + ti_max * 0.01, ax.get_ylim()[1] * 0.02 if ax.get_ylim()[1] > 0 else 0.01,
                                f"null\n{null_ti:.0f}ms", color=color, fontsize=7, va='bottom')
            ax.axhline(y=0, color='#3a424d', linewidth=0.8, alpha=0.5)
            ax.axvline(x=TI, color='yellow', linestyle='--', alpha=0.8, label=f'TI={TI:.0f}')
            ax.set_xlabel('TI (ms)', color='white')
            ax.set_ylabel('Signal (a.u.)', color='white')
            ax.set_title('IR Signal vs TI  (— magnitude · - - signed)', color='white', fontsize=10)
            ax.legend(fontsize=8, facecolor=C_CHIP, edgecolor=C_BORDER, labelcolor=C_TEXT, framealpha=0.95)

        elif mode == "Contrast Map":
            # 2-D WM–GM CNR heat map vs TR and TE for the current sequence
            tr_vals = np.logspace(np.log10(200), np.log10(6000), 80)
            te_vals = np.linspace(5, 200, 60)
            TR_g, TE_g = np.meshgrid(tr_vals, te_vals)
            wm = TISSUES_B0["white_matter"]; gm = TISSUES_B0["gray_matter"]
            s_wm = self._curve_signal(seq, wm, TR_g, TE_g, TI, FA)
            s_gm = self._curve_signal(seq, gm, TR_g, TE_g, TI, FA)
            cnr_map = np.abs(s_wm - s_gm)
            ax.imshow(cnr_map, origin='lower', aspect='auto', cmap='hot',
                      extent=[np.log10(200), np.log10(6000), 5, 200], vmin=0)
            ax.plot([np.log10(TR)], [TE], 'c+', markersize=12, markeredgewidth=2, label=f'TR={TR:.0f} TE={TE:.0f}')
            tick_trs = [200, 500, 1000, 2000, 4000]
            ax.set_xticks([np.log10(v) for v in tick_trs])
            ax.set_xticklabels([str(v) for v in tick_trs])
            ax.set_xlabel('TR (ms, log scale)', color='white')
            ax.set_ylabel('TE (ms)', color='white')
            ax.set_title('WM–GM CNR map  (brighter = better contrast)', color='white', fontsize=10)
            ax.legend(fontsize=8, facecolor=C_CHIP, edgecolor=C_BORDER, labelcolor=C_TEXT, framealpha=0.95)

        elif mode == "Histogram":
            img = self.current_image
            if img is not None and img.size > 0:
                img_pos = img.ravel()
                img_pos = img_pos[img_pos > 0]
                if img_pos.size > 0:
                    ax.hist(img_pos, bins=80, color=C_ACCENT, alpha=0.7, density=True)
                    # Annotate tissue ROI means using TISSUES_B0
                    _tissue_rows = [("WM", '#ff6b6b', "white_matter"),
                                    ("GM", '#69db7c', "gray_matter"),
                                    ("CSF", '#74c0fc', "csf")]
                    ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 1.0
                    for tlabel, color, key in _tissue_rows:
                        props = TISSUES_B0[key]
                        mean_sig = float(self._curve_signal(seq, props, TR, TE, TI, FA))
                        ax.axvline(x=mean_sig, color=color, linestyle='--', linewidth=1.5, alpha=0.85,
                                   label=f'{tlabel}≈{mean_sig:.3f}')
                    ax.set_xlabel('Pixel Value', color='white')
                    ax.set_ylabel('Density', color='white')
                    ax.set_title('Image Histogram  (dashed = tissue signal prediction)',
                                 color='white', fontsize=10)
                    ax.legend(fontsize=8, facecolor=C_CHIP, edgecolor=C_BORDER, labelcolor=C_TEXT, framealpha=0.95)
                else:
                    ax.text(0.5, 0.5, 'No image data', ha='center', va='center',
                            transform=ax.transAxes, color='white')
            else:
                ax.text(0.5, 0.5, 'Run simulation first', ha='center', va='center',
                        transform=ax.transAxes, color='white')

        else:  # TE decay (default)
            te_range = np.arange(5, min(300, TR), 2)
            _tissue_rows = [("White Matter", '#ff6b6b', "white_matter"),
                            ("Gray Matter",  '#69db7c', "gray_matter"),
                            ("CSF",          '#74c0fc', "csf")]
            for tlabel, color, key in _tissue_rows:
                props = TISSUES_B0[key]
                sig = self._curve_signal(seq, props, TR, te_range, TI, FA)
                ax.plot(te_range, sig, color=color, linewidth=2, label=tlabel)

            ax.axvline(x=TE, color='yellow', linestyle='--', alpha=0.7, label=f'TE={TE:.0f}')
            if seq == "Gradient Echo":
                ernst_gm = float(np.degrees(np.arccos(np.clip(np.exp(-TR / 1330), -1.0, 1.0))))
                ax.set_title(f'GRE T2* Decay  (Ernst≈{ernst_gm:.0f}° for GM at this TR)',
                             color='white', fontsize=10)
            elif seq == "Inversion Recovery":
                ax.set_title(f'IR T2 Decay at TI={TI:.0f}ms  (use TI sweep for null points)',
                             color='white', fontsize=10)
            elif seq == "Balanced SSFP":
                ax.set_title('bSSFP Signal vs TE  (T2/T1 — bright fluid)', color='white', fontsize=10)
            elif seq == "Echo Planar (EPI)":
                ax.set_title('EPI T2* Decay  (signal vs TE)', color='white', fontsize=10)
            else:
                ax.set_title('T2 Decay  (signal vs TE)', color='white', fontsize=11)
            ax.set_xlabel('TE (ms)', color='white')
            ax.set_ylabel('Signal (a.u.)', color='white')
            ax.legend(fontsize=8, facecolor=C_CHIP, edgecolor=C_BORDER, labelcolor=C_TEXT, framealpha=0.95)
        ax = self.axes[1]
        ax.set_facecolor(C_HEADER)
        ax.tick_params(colors=C_TEXT_DIM, labelsize=8, length=3)
        for _s in ax.spines.values():
            _s.set_color(C_BORDER)
        ax.grid(True, color="#202830", linewidth=0.6, alpha=0.9)
        ax.set_axisbelow(True)
