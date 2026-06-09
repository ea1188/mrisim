"""
tissue_db.py  —  single authoritative source of MR tissue relaxation properties.

Consolidates the previously scattered tables (phantom3d.TISSUE_PROPERTIES_3D,
body_phantoms.BODY_TISSUES, nifti_region.EXTRA_MR_PROPERTIES) into one place,
with values at BOTH 1.5 T and 3.0 T so the simulator can model field strength —
the most distinctly-MR control there is.

3.0 T abdominal/pelvic values follow de Bazelaire et al., Radiology 2004
(kidney cortex T1 1142/T2 76, liver T1 809/T2 34, spleen T1 1328/T2 61,
pancreas T1 725/T2 43, paravertebral muscle T1 898/T2 29, L4 marrow T1 586/T2 49,
subcutaneous fat T1 382/T2 68). Neuro values follow commonly cited 1.5/3 T
references (Stanisz et al. 2005; Wansapura et al. 1999). 1.5 T values use the
measured 1.5 T figures where available, otherwise the established rule that T1
shortens and T2 lengthens modestly at lower field.

Each label maps to a dict with keys T1, T2, PD, T2star (ms / fraction), and a
display name. Integer labels are the simulator's shared vocabulary:

  0 Air      1 Fluid/CSF   2 Gray matter  3 White matter  4 Fat   5 Bone(skull)
  6 Muscle   7 Liver       8 Spleen       9 Kidney cortex  10 Kidney medulla
  11 Blood   12 Gas        13 Cortical bone  14 Marrow      15 Cartilage/Disc
  16 Spinal cord  17 Bowel/GI  18 Lung  19 Pancreas  20 Heart/Myocardium
  21 Soft tissue/Gland
"""

# (T1_1.5T, T2_1.5T, T1_3T, T2_3T, PD, T2star_3T, name)
_RAW = {
    0:  (1,    1,    1,    1,    0.00, 1,    "Air/Background"),
    1:  (4200, 2000, 4500, 2200, 1.00, 1000, "Fluid/CSF"),
    2:  (920,  100,  1330, 80,   0.80, 60,   "Gray matter"),
    3:  (580,  90,   830,  70,   0.65, 48,   "White matter"),
    4:  (290,  165,  382,  68,   0.95, 45,   "Fat"),
    5:  (220,  4,    250,  3,    0.10, 2,    "Bone (skull)"),
    6:  (870,  47,   898,  29,   0.75, 24,   "Muscle"),
    7:  (586,  46,   809,  34,   0.78, 28,   "Liver"),
    8:  (1057, 79,   1328, 61,   0.85, 50,   "Spleen"),
    9:  (966,  87,   1142, 76,   0.82, 58,   "Kidney cortex"),
    10: (1412, 85,   1545, 81,   0.82, 62,   "Kidney medulla"),
    11: (1441, 290,  1900, 275,  0.95, 200,  "Blood"),
    12: (1,    1,    1,    1,    0.02, 1,    "Gas"),
    13: (220,  3,    250,  2,    0.08, 1,    "Cortical bone"),
    14: (288,  62,   586,  49,   0.92, 40,   "Marrow"),
    15: (1024, 30,   1100, 28,   0.72, 24,   "Cartilage/Disc"),
    16: (745,  74,   993,  78,   0.72, 55,   "Spinal cord"),
    17: (1031, 47,   1200, 40,   0.74, 32,   "Bowel/GI"),
    18: (830,  30,   1270, 23,   0.12, 8,    "Lung"),
    19: (584,  46,   725,  43,   0.75, 30,   "Pancreas"),
    20: (1030, 40,   1471, 47,   0.80, 35,   "Heart/Myocardium"),
    21: (900,  55,   1100, 50,   0.78, 42,   "Soft tissue/Gland"),
    # Dense fibrous tissue — menisci, ligaments, tendons. Very short T2 → dark on
    # every sequence (the classic "black" of a meniscus or the patellar tendon).
    22: (920,  8,    1000, 6,    0.40, 5,    "Ligament/Meniscus"),
    # Demyelinating white-matter lesion (e.g. MS plaque) — raised free water, so
    # T1 and T2 both lengthen relative to white matter. The teaching point: its
    # T1 sits close enough to WM that it nearly vanishes on a T1-weighted scan,
    # yet its long T2 makes it bright on T2/FLAIR. Used by the browser "add a
    # lesion" demo (painted into brain WM); not part of any body phantom.
    23: (1100, 150,  1350, 180,  0.82, 120,  "Lesion (WM)"),
    # --- Browser demo pathologies (brain-only; see web_adapter). Each is tuned so
    #     a *specific* sequence reveals it — the rest of its behaviour (restricted
    #     diffusion, paramagnetic susceptibility, Gd uptake) lives in the diffusion,
    #     b0 and gadolinium tables keyed by these same labels. ---
    # Acute infarct: cytotoxic oedema. Mild T1/T2 lengthening; the giveaway is
    # restricted diffusion (low ADC) → bright on DWI, dark on the ADC map.
    24: (1100, 95,   1300, 110,  0.80, 80,   "Acute infarct"),
    # Microhaemorrhage: blood-breakdown products are strongly paramagnetic, so a
    # very short T2* makes it bloom dark on SWI / gradient echo.
    25: (900,  46,   1000, 40,   0.70, 8,    "Microhaemorrhage"),
    # Enhancing tumour: long T1/T2 (cellular + oedema); breaks the blood–brain
    # barrier, so it takes up gadolinium and brightens on T1-post-contrast.
    26: (1300, 100,  1600, 120,  0.85, 90,   "Tumour (enhancing)"),
}

FIELD_STRENGTHS = ["1.5T", "3T"]


def properties(field: str = "3T") -> dict[int, dict]:
    """Return {label: {T1,T2,PD,T2star,name}} for the requested field strength."""
    use3t = (field == "3T")
    out = {}
    for lab, (t1_15, t2_15, t1_3, t2_3, pd, t2s, name) in _RAW.items():
        out[lab] = {
            "T1": t1_3 if use3t else t1_15,
            "T2": t2_3 if use3t else t2_15,
            "PD": pd,
            # T2* scales with T2 between fields; given value is at 3T.
            "T2star": t2s if use3t else max(1, int(t2s * (t2_15 / t2_3) if t2_3 else t2s)),
            "name": name,
        }
    return out


def apply_to_engine(field: str = "3T") -> dict[int, dict]:
    """Overwrite phantom3d.TISSUE_PROPERTIES_3D with the chosen field's values.

    Replaces (not just fills) brain labels 0-5 and adds body labels 6-21, so the
    whole simulator renders at a single, consistent field strength.
    """
    import phantom3d
    props = properties(field)
    phantom3d.TISSUE_PROPERTIES_3D.clear()
    phantom3d.TISSUE_PROPERTIES_3D.update(props)
    return props
