#!/usr/bin/env python3
"""Generate the MRISim validation benchmark report (docs/VALIDATION.md).

Documents, in one human-readable place, that the engine's quantitative behaviour
matches the literature it was built from: measured tissue relaxation at 1.5 T and
3 T vs published means, the contrast/nulling each clinical weighting should
produce (from the same closed-form equations the images use), and the analytic
landmarks (Ernst angle, FLAIR/STIR null TI, bSSFP banding null, fat–water shift).

Deterministic and self-checking: every row carries a PASS/FAIL against a
tolerance, and `tests/test_validation_report.py` fails if any check regresses, so
the report cannot silently drift from the physics.

Run:  python scripts/validation_report.py        # writes docs/VALIDATION.md
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

import numpy as np

import tissue_db
from signal_engine import (spin_echo_signal, inversion_recovery_signal,
                           balanced_ssfp_signal, ssfp_banding)
from dixon import fat_water_shift_hz

GAMMA = 42.577  # MHz/T

# Published relaxation means (ms). 3 T neuro: Wansapura 1999 / Stanisz 2005;
# 3 T body: de Bazelaire 2004. 1.5 T: commonly cited clinical means.
#   label: {"1.5T": (T1, T2), "3T": (T1, T2), "ref": citation}
REF_RELAX = {
    1:  {"1.5T": (4200, 2000), "3T": (4500, 2200), "ref": "CSF (Condon 1987; Spijkerman 2018)"},
    2:  {"1.5T": (920, 100),   "3T": (1330, 80),   "ref": "Gray matter (Wansapura 1999; Stanisz 2005)"},
    3:  {"1.5T": (580, 90),    "3T": (830, 70),    "ref": "White matter (Wansapura 1999; Stanisz 2005)"},
    4:  {"1.5T": (290, 165),   "3T": (382, 68),    "ref": "Subcutaneous fat (de Bazelaire 2004)"},
    6:  {"1.5T": (870, 47),    "3T": (898, 29),    "ref": "Skeletal muscle (de Bazelaire 2004)"},
    7:  {"1.5T": (586, 46),    "3T": (809, 34),    "ref": "Liver (de Bazelaire 2004)"},
    8:  {"1.5T": (1057, 79),   "3T": (1328, 61),   "ref": "Spleen (de Bazelaire 2004)"},
    9:  {"1.5T": (966, 87),    "3T": (1142, 76),   "ref": "Kidney cortex (de Bazelaire 2004)"},
    11: {"1.5T": (1441, 290),  "3T": (1900, 275),  "ref": "Arterial blood (Stanisz 2005; Lu 2004)"},
    20: {"1.5T": (1030, 40),   "3T": (1471, 47),   "ref": "Myocardium (de Bazelaire 2004)"},
}
RELAX_TOL = 0.12   # ±12 % vs the published mean (relaxometry spread is real)

PASS, FAIL = "✅", "❌"


def _row(cells):
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _ok(rows):
    return all(r for r in rows)


# --------------------------------------------------------------------------- #
def relaxation_section():
    lines = ["## 1. Tissue relaxation vs. published literature", "",
             "The engine's tissue tables (`tissue_db`) are sourced directly from these "
             "references; this section re-confirms each value is carried unaltered "
             "(within tolerance) and shows the expected field trend — T1 lengthens from "
             "1.5 T → 3 T for soft tissue.", "",
             _row(["Tissue", "Field", "T1 engine / ref (ms)", "ΔT1",
                   "T2 engine / ref (ms)", "ΔT2", "OK"]),
             _row(["---"] * 7)]
    oks = []
    for field in ("1.5T", "3T"):
        props = tissue_db.properties(field)
        for lab, ref in REF_RELAX.items():
            t1, t2 = props[lab]["T1"], props[lab]["T2"]
            rt1, rt2 = ref[field]
            d1, d2 = (t1 - rt1) / rt1, (t2 - rt2) / rt2
            ok = abs(d1) <= RELAX_TOL and abs(d2) <= RELAX_TOL
            oks.append(ok)
            lines.append(_row([props[lab]["name"], field, f"{t1} / {rt1}", f"{d1:+.0%}",
                               f"{t2} / {rt2}", f"{d2:+.0%}", PASS if ok else FAIL]))
    lines += ["", "References: " + "; ".join(sorted({r["ref"].split(" (")[1][:-1]
              for r in REF_RELAX.values()})) + "."]
    return "\n".join(lines), _ok(oks)


def _se(lab, field, TR, TE):
    p = tissue_db.properties(field)[lab]
    return spin_echo_signal(p["T1"], p["T2"], p["PD"], TR, TE)


def contrast_section():
    lines = ["## 2. Contrast & nulling (closed-form, the same equations the images use)", "",
             "Per-tissue spin-echo / inversion-recovery signal at 3 T for each clinical "
             "weighting, checking the ordering and nulls a radiologist expects.", "",
             _row(["Weighting", "Protocol", "Expectation", "Computed (WM, GM, CSF, fat)", "OK"]),
             _row(["---"] * 5)]
    oks = []

    def sig4(fn):
        return [fn(3), fn(2), fn(1), fn(4)]   # WM, GM, CSF, fat (labels)

    # T1-weighted SE: WM brightest, CSF dark.
    s = sig4(lambda lab: _se(lab, "3T", 500, 12))
    ok = s[0] > s[1] > s[2]
    oks.append(ok)
    lines.append(_row(["T1w SE", "TR 500 / TE 12", "WM > GM > CSF",
                       ", ".join(f"{v:.2f}" for v in s), PASS if ok else FAIL]))

    # T2-weighted SE: CSF brightest.
    s = sig4(lambda lab: _se(lab, "3T", 4000, 100))
    ok = s[2] > s[1] > s[0]
    oks.append(ok)
    lines.append(_row(["T2w SE", "TR 4000 / TE 100", "CSF > GM > WM",
                       ", ".join(f"{v:.2f}" for v in s), PASS if ok else FAIL]))

    # Proton-density SE: GM > WM, low T2 weighting.
    s = sig4(lambda lab: _se(lab, "3T", 4000, 12))
    ok = s[1] > s[0]
    oks.append(ok)
    lines.append(_row(["PDw SE", "TR 4000 / TE 12", "GM > WM",
                       ", ".join(f"{v:.2f}" for v in s), PASS if ok else FAIL]))

    # FLAIR: CSF nulled (TI from -T1 ln((1+e^{-TR/T1})/2)).
    p = tissue_db.properties("3T")
    T1_csf, TR = p[1]["T1"], 9000
    ti = -T1_csf * np.log((1 + np.exp(-TR / T1_csf)) / 2)
    csf = abs(inversion_recovery_signal(p[1]["T1"], p[1]["T2"], p[1]["PD"], TR, 100, ti))
    gm = abs(inversion_recovery_signal(p[2]["T1"], p[2]["T2"], p[2]["PD"], TR, 100, ti))
    ok = csf < 0.05 * gm
    oks.append(ok)
    lines.append(_row(["FLAIR", f"TR 9000 / TI {ti:.0f} / TE 100", "CSF nulled (≪ GM)",
                       f"CSF {csf:.3f} vs GM {gm:.2f}", PASS if ok else FAIL]))

    # STIR: fat nulled at TI ≈ T1_fat·ln2 (TR ≫ T1).
    T1_fat = p[4]["T1"]
    ti_f = T1_fat * np.log(2)
    fat = abs(inversion_recovery_signal(p[4]["T1"], p[4]["T2"], p[4]["PD"], 6000, 30, ti_f))
    wm = abs(inversion_recovery_signal(p[3]["T1"], p[3]["T2"], p[3]["PD"], 6000, 30, ti_f))
    ok = fat < 0.05 * wm
    oks.append(ok)
    lines.append(_row(["STIR", f"TR 6000 / TI {ti_f:.0f} / TE 30", "Fat nulled (≪ WM)",
                       f"Fat {fat:.3f} vs WM {wm:.2f}", PASS if ok else FAIL]))
    return "\n".join(lines), _ok(oks)


def landmarks_section():
    lines = ["## 3. Analytic landmarks", "",
             _row(["Quantity", "Formula", "Expected", "Computed", "OK"]),
             _row(["---"] * 5)]
    oks = []

    # Ernst angle for WM at TR 30: arccos(exp(-TR/T1)).
    T1 = tissue_db.properties("3T")[3]["T1"]
    ernst = np.degrees(np.arccos(np.exp(-30 / T1)))
    ok = 13 <= ernst <= 16
    oks.append(ok)
    lines.append(_row(["Ernst angle (WM, TR 30)", "arccos(e^(−TR/T1))", "≈ 14–15°",
                       f"{ernst:.1f}°", PASS if ok else FAIL]))

    # bSSFP banding null at Δf = 1/(2·TR).
    TR = 5.0
    null_f = 1.0 / (2 * TR * 1e-3)
    on = ssfp_banding(0.0, TR, np.exp(-TR / 2200))
    null = ssfp_banding(null_f, TR, np.exp(-TR / 2200))
    ok = on > 0.95 and null < 0.15
    oks.append(ok)
    lines.append(_row(["bSSFP banding null (TR 5)", "Δf = 1/(2·TR)", f"{null_f:.0f} Hz, deep null",
                       f"on {on:.2f} / null {null:.2f}", PASS if ok else FAIL]))

    # Fat–water shift at 3 T: 3.5 ppm × γ × B0.
    fw = fat_water_shift_hz(3.0)
    expect = 3.5 * GAMMA * 3.0
    ok = abs(fw - expect) / expect < 0.05
    oks.append(ok)
    lines.append(_row(["Fat–water shift @ 3 T", "3.5 ppm × γ × B0", f"≈ {expect:.0f} Hz",
                       f"{fw:.0f} Hz", PASS if ok else FAIL]))

    # bSSFP fluid-bright (∝ T2/T1): CSF ≫ WM.
    p = tissue_db.properties("3T")
    csf = balanced_ssfp_signal(p[1]["T1"], p[1]["T2"], p[1]["PD"], 5, 2.5, 45)
    wm = balanced_ssfp_signal(p[3]["T1"], p[3]["T2"], p[3]["PD"], 5, 2.5, 45)
    ok = csf > 2 * wm
    oks.append(ok)
    lines.append(_row(["bSSFP fluid-bright", "S ∝ T2/T1", "CSF ≫ WM",
                       f"CSF {csf:.2f} / WM {wm:.2f}", PASS if ok else FAIL]))
    return "\n".join(lines), _ok(oks)


def scaling_section():
    return ("## 4. SNR & scan-time scaling laws\n\n"
            "The calibrated Rician-noise SNR model scales SNR with the voxel volume, "
            "√NEX, 1/√bandwidth, √R·g (parallel imaging) and field strength; scan time "
            "scales with phase-encodes × NEX ÷ ETL ÷ R. These laws are verified "
            "empirically end-to-end in `tests/test_validation.py` "
            "(`test_snr_scales_with_*`, `test_scan_time_scales_with_*`) and the 3-D "
            "√Nz gain in `tests/test_physics_validation.py`.", True)


def build_report():
    secs = [relaxation_section(), contrast_section(), landmarks_section(), scaling_section()]
    all_ok = all(ok for _, ok in secs)
    header = [
        "# MRISim — validation benchmark report", "",
        f"_Generated by `scripts/validation_report.py` on {date.today().isoformat()}; "
        "regenerate after any physics change._", "",
        f"**Overall: {PASS + ' all checks pass' if all_ok else FAIL + ' regressions present'}.** "
        "Every value below is produced by the engine and compared to a published "
        "reference or closed-form result with a PASS/FAIL tolerance; the companion "
        "test (`tests/test_validation_report.py`) fails if any check regresses.", "",
    ]
    return "\n".join(header) + "\n\n".join(s for s, _ in secs) + "\n", all_ok


def main():
    md, ok = build_report()
    out = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "VALIDATION.md")
    with open(out, "w") as f:
        f.write(md)
    print(f"wrote {out} ({'all pass' if ok else 'REGRESSIONS'})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
