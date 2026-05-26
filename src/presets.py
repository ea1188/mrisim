"""Clinical protocol presets for common MRI examinations."""

PRESETS = {
    "Brain T1 SE": {
        "sequence": "Spin Echo",
        "TR": 500,
        "TE": 15,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 240,
        "bandwidth": 125,
        "NEX": 1,
        "description": "Standard T1-weighted spin echo. Short TR/TE for T1 contrast. WM bright, GM intermediate, CSF dark."
    },
    "Brain T2 SE": {
        "sequence": "Spin Echo",
        "TR": 4000,
        "TE": 100,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 240,
        "bandwidth": 125,
        "NEX": 1,
        "description": "T2-weighted spin echo. Long TR/TE. CSF bright, pathology bright, WM dark."
    },
    "Brain PD": {
        "sequence": "Spin Echo",
        "TR": 3000,
        "TE": 15,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 240,
        "bandwidth": 125,
        "NEX": 1,
        "description": "Proton density weighted. Long TR, short TE. Contrast based on hydrogen density."
    },
    "Brain FLAIR": {
        "sequence": "Inversion Recovery",
        "TR": 9000,
        "TE": 90,
        "TI": 2548,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 240,
        "bandwidth": 125,
        "NEX": 1,
        "description": "FLAIR: CSF nulled at TI=2548ms (= T1_CSF·ln(2/(1+e^-TR/T1)) at 3T). Periventricular lesions bright."
    },
    "Brain STIR": {
        "sequence": "Inversion Recovery",
        "TR": 5000,
        "TE": 30,
        "TI": 265,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 240,
        "bandwidth": 125,
        "NEX": 1,
        "description": "STIR: Fat nulled at TI=265ms (= T1_fat·ln(2) at 3T, T1_fat=382ms). Fluid and edema bright."
    },
    "Brain MPRAGE": {
        "sequence": "Inversion Recovery",
        "TR": 2500,
        "TE": 3,
        "TI": 900,
        "flip_angle": 8,
        "matrix_size": 256,
        "FOV": 240,
        "bandwidth": 200,
        "NEX": 1,
        "description": "MPRAGE (MP-RAGE): standard 3D T1w at 3T. TI=900ms maximises WM/GM contrast. WM bright, GM intermediate, CSF dark. Gold standard for cortical morphometry."
    },
    "Brain SWI": {
        "sequence": "Gradient Echo",
        "TR": 28,
        "TE": 20,
        "TI": 150,
        "flip_angle": 15,
        "matrix_size": 256,
        "FOV": 240,
        "bandwidth": 125,
        "NEX": 1,
        "description": "Susceptibility-weighted imaging (SWI). Long TE amplifies phase differences from iron, blood products, calcification. Microbleeds, venous blood appear dark."
    },
    "Brain GRE T2*": {
        "sequence": "Gradient Echo",
        "TR": 600,
        "TE": 20,
        "TI": 150,
        "flip_angle": 20,
        "matrix_size": 256,
        "FOV": 240,
        "bandwidth": 125,
        "NEX": 1,
        "description": "T2*-weighted GRE. Sensitive to susceptibility (blood products, calcification, iron)."
    },
    "Brain GRE T1": {
        "sequence": "Gradient Echo",
        "TR": 250,
        "TE": 5,
        "TI": 150,
        "flip_angle": 70,
        "matrix_size": 256,
        "FOV": 240,
        "bandwidth": 200,
        "NEX": 1,
        "description": "T1-weighted GRE. Fast acquisition, good for post-contrast imaging."
    },
    "DWI Stroke": {
        "sequence": "Diffusion (DWI)",
        "TR": 8000,
        "TE": 80,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 128,
        "FOV": 240,
        "bandwidth": 250,
        "NEX": 2,
        "b_value": 1000,
        "diff_direction": "Left-Right",
        "diff_display": "DWI",
        "description": "Standard DWI for acute stroke detection. b=1000, restricted diffusion appears bright."
    },
    "DWI High-b": {
        "sequence": "Diffusion (DWI)",
        "TR": 8000,
        "TE": 90,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 128,
        "FOV": 240,
        "bandwidth": 250,
        "NEX": 4,
        "b_value": 2000,
        "diff_direction": "Left-Right",
        "diff_display": "DWI",
        "description": "High b-value DWI. Better conspicuity for small lesions, more T2 shine-through suppression."
    },
    "ADC Map": {
        "sequence": "Diffusion (DWI)",
        "TR": 8000,
        "TE": 80,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 128,
        "FOV": 240,
        "bandwidth": 250,
        "NEX": 2,
        "b_value": 1000,
        "diff_direction": "Left-Right",
        "diff_display": "ADC Map",
        "description": "ADC map. Quantitative diffusion. Restricted diffusion = low ADC (dark). CSF = high ADC (bright)."
    },
    "TOF MRA Circle of Willis": {
        "sequence": "MR Angiography",
        "TR": 25,
        "TE": 4,
        "TI": 150,
        "flip_angle": 60,
        "matrix_size": 256,
        "FOV": 200,
        "bandwidth": 200,
        "NEX": 1,
        "angio_type": "TOF",
        "angio_mip_slab": 30,
        "description": "TOF MRA with MIP. Short TR saturates background, fresh blood is bright. FA=60° optimal."
    },
    "TOF MRA Thin Slab": {
        "sequence": "MR Angiography",
        "TR": 25,
        "TE": 4,
        "TI": 150,
        "flip_angle": 60,
        "matrix_size": 256,
        "FOV": 200,
        "bandwidth": 200,
        "NEX": 1,
        "angio_type": "TOF",
        "angio_mip_slab": 5,
        "description": "Thin slab TOF. Less vessel overlap, better for individual slice anatomy."
    },
    "fMRI BOLD Standard": {
        "sequence": "fMRI (BOLD)",
        "TR": 2000,
        "TE": 30,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 64,
        "FOV": 240,
        "bandwidth": 250,
        "NEX": 1,
        "fmri_display": "T-statistic Map",
        "fmri_volumes": 200,
        "fmri_threshold": 3,
        "description": "Standard fMRI. TE=30ms optimal for BOLD at 3T (matches T2* of gray matter)."
    },
    "fMRI High Resolution": {
        "sequence": "fMRI (BOLD)",
        "TR": 3000,
        "TE": 30,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 128,
        "FOV": 200,
        "bandwidth": 200,
        "NEX": 1,
        "fmri_display": "T-statistic Map",
        "fmri_volumes": 150,
        "fmri_threshold": 3,
        "description": "Higher resolution fMRI. Better spatial localization, longer TR reduces temporal sampling."
    },

    # ------------------------------------------------------------------ #
    #  Abdomen  (FOV 380 mm — matches native atlas extent)
    # ------------------------------------------------------------------ #
    "Abdomen T1 GRE": {
        "sequence": "Gradient Echo",
        "TR": 200,
        "TE": 4,
        "TI": 150,
        "flip_angle": 70,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 500,
        "NEX": 1,
        "description": "T1-weighted GRE (VIBE-like). Liver, spleen, kidneys well-delineated. Enhancing lesions bright post-contrast. Short breath-hold."
    },
    "Abdomen T2 FSE": {
        "sequence": "FSE / TSE",
        "TR": 4000,
        "TE": 90,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 500,
        "NEX": 2,
        "etl": 32,
        "echo_spacing": 8,
        "description": "T2-weighted FSE abdomen. Fluid (bile, pancreatic duct, ascites) appears bright. Cysts vs solid lesions."
    },
    "Abdomen STIR": {
        "sequence": "Inversion Recovery",
        "TR": 5000,
        "TE": 60,
        "TI": 265,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 250,
        "NEX": 2,
        "description": "STIR abdomen. TI=265ms nulls fat at 3T. Lymph nodes, inflammation, and edema appear bright against dark fat background."
    },
    "Abdomen DWI": {
        "sequence": "Diffusion (DWI)",
        "TR": 6000,
        "TE": 60,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 128,
        "FOV": 380,
        "bandwidth": 250,
        "NEX": 4,
        "b_value": 800,
        "diff_direction": "Left-Right",
        "diff_display": "DWI",
        "description": "Abdominal DWI b=800. Malignant lesions (HCC, metastases) restrict diffusion — bright DWI, low ADC. Liver characterisation."
    },
    "MRCP": {
        "sequence": "FSE / TSE",
        "TR": 8000,
        "TE": 300,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 125,
        "NEX": 2,
        "etl": 32,
        "echo_spacing": 10,
        "description": "Heavily T2-weighted MRCP. Very long TE suppresses all tissue; bile duct and pancreatic duct appear as bright fluid against dark background."
    },

    # ------------------------------------------------------------------ #
    #  Spine  (FOV 380 mm — same atlas as Abdomen, full T/L spine)
    # ------------------------------------------------------------------ #
    "Spine T1 Sagittal": {
        "sequence": "Spin Echo",
        "TR": 600,
        "TE": 15,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 125,
        "NEX": 2,
        "description": "Sagittal T1w spine. Normal marrow fat bright. Disc herniation, marrow infiltration (metastases appear dark)."
    },
    "Spine T2 Sagittal": {
        "sequence": "FSE / TSE",
        "TR": 4000,
        "TE": 110,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 125,
        "NEX": 2,
        "etl": 16,
        "echo_spacing": 10,
        "description": "Sagittal T2w FSE (clinical standard). CSF bright, spinal cord intermediate. Disc dehydration, cord compression, myelopathy."
    },
    "Spine STIR": {
        "sequence": "Inversion Recovery",
        "TR": 4000,
        "TE": 30,
        "TI": 265,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 125,
        "NEX": 2,
        "description": "Sagittal STIR spine. Fat-suppressed — marrow fat dark. Highly sensitive for bone marrow edema, fractures, metastases, discitis."
    },
    "Spine Axial T2": {
        "sequence": "FSE / TSE",
        "TR": 3500,
        "TE": 100,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 200,
        "NEX": 2,
        "etl": 16,
        "echo_spacing": 10,
        "description": "Axial T2w at disc level. Nerve root compression, foraminal stenosis, cord morphology. Complement to sagittal survey."
    },

    # ------------------------------------------------------------------ #
    #  Pelvis  (FOV 380 mm)
    # ------------------------------------------------------------------ #
    "Pelvis T1 SE": {
        "sequence": "Spin Echo",
        "TR": 600,
        "TE": 15,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 125,
        "NEX": 2,
        "description": "T1w pelvis. Bone marrow and fat bright. Lymph node staging, anatomic survey before targeted sequences."
    },
    "Pelvis T2 High-Res": {
        "sequence": "FSE / TSE",
        "TR": 5000,
        "TE": 100,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 125,
        "NEX": 2,
        "etl": 16,
        "echo_spacing": 10,
        "description": "High-resolution T2w FSE pelvis. Clinical standard for prostate and uterine cancer staging. Zonal anatomy, capsule, invasion."
    },
    "Pelvis STIR": {
        "sequence": "Inversion Recovery",
        "TR": 5000,
        "TE": 40,
        "TI": 265,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 125,
        "NEX": 2,
        "description": "STIR pelvis. Fat suppressed. Sacral insufficiency fractures, AVN femoral heads, marrow edema, soft-tissue inflammation."
    },
    "Pelvis DWI": {
        "sequence": "Diffusion (DWI)",
        "TR": 6000,
        "TE": 80,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 128,
        "FOV": 380,
        "bandwidth": 250,
        "NEX": 4,
        "b_value": 800,
        "diff_direction": "Left-Right",
        "diff_display": "DWI",
        "description": "Pelvic DWI b=800. Prostate cancer, cervical/endometrial cancer, and lymph nodes restrict diffusion. Combined with T2 for PI-RADS scoring."
    },

    # ------------------------------------------------------------------ #
    #  Knee  (FOV 150 mm — dedicated small joint)
    # ------------------------------------------------------------------ #
    "Knee PD FSE": {
        "sequence": "FSE / TSE",
        "TR": 3500,
        "TE": 30,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 150,
        "bandwidth": 200,
        "NEX": 2,
        "etl": 8,
        "echo_spacing": 10,
        "description": "PD-weighted FSE (clinical knee standard). Balanced fluid/cartilage contrast. Meniscal tears appear as linear signal. ACL, PCL assessment."
    },
    "Knee T2 Fat-Sat": {
        "sequence": "Inversion Recovery",
        "TR": 4000,
        "TE": 60,
        "TI": 265,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 150,
        "bandwidth": 200,
        "NEX": 1,
        "description": "T2 fat-saturated knee (STIR). Bone marrow edema bright. Bone contusions, stress fractures, cartilage defects, ligament tears."
    },
    "Knee GRE T2*": {
        "sequence": "Gradient Echo",
        "TR": 500,
        "TE": 20,
        "TI": 150,
        "flip_angle": 30,
        "matrix_size": 256,
        "FOV": 150,
        "bandwidth": 250,
        "NEX": 1,
        "description": "GRE T2* knee. Articular cartilage mapping. Sensitive to calcifications, haemosiderin, loose bodies. 3D acquisition for MPR."
    },
}

_REGION_PREFIXES: list[tuple[str, str]] = [
    ("Abdomen", "Abdomen"), ("Spine", "Spine"), ("Pelvis", "Pelvis"),
    ("Knee", "Knee"), ("Brain", "Brain"), ("MRCP", "Abdomen"),
    ("DWI", "Brain"), ("ADC", "Brain"), ("TOF", "Brain"), ("fMRI", "Brain"),
]


def get_preset_region(name: str) -> str | None:
    """Return the anatomy region for a preset, or None if unknown."""
    for prefix, region in _REGION_PREFIXES:
        if name.startswith(prefix):
            return region
    return None


def get_preset_names() -> list[str]:
    """Return list of preset names grouped by category."""
    return list(PRESETS.keys())


def get_preset(name: str) -> dict | None:
    """Return preset parameters dictionary."""
    return PRESETS.get(name, None)


def estimate_sar(flip_angle: float, TR: float, num_slices: int = 20, sequence: str = "SE") -> dict[str, float | bool]:
    """Estimate SAR (Specific Absorption Rate) in W/kg.
    
    SAR is proportional to:
    - (flip_angle)^2
    - Number of RF pulses per unit time (1/TR * num_slices)
    - Duty cycle
    
    Returns estimated whole-body SAR and head SAR.
    """
    # SAR proportional to B1^2 which is proportional to flip_angle^2
    # Reference: 90° pulse at TR=500ms, 20 slices ≈ 2 W/kg (typical 3T)
    
    reference_sar = 2.0  # W/kg at reference conditions
    reference_fa = 90
    reference_tr = 500
    reference_slices = 20
    
    # Scale factors
    fa_factor = (flip_angle / reference_fa) ** 2
    tr_factor = reference_tr / max(TR, 10)  # more pulses per second = more SAR
    slice_factor = num_slices / reference_slices
    
    # Sequence-dependent RF factor
    seq_factors = {
        "SE": 1.5,      # 90° + 180° refocusing
        "GRE": 0.5,     # Only excitation pulse
        "IR": 2.0,      # Inversion + 90° + 180°
        "EPI": 0.5,     # Single excitation
        "Diffusion": 1.5,  # 90° + 180° + diffusion gradients
    }
    seq_factor = seq_factors.get(sequence, 1.0)
    
    whole_body_sar = reference_sar * fa_factor * tr_factor * slice_factor * seq_factor
    head_sar = whole_body_sar * 2.5  # Head SAR typically 2-3x whole body
    
    # FDA limits: 3 W/kg whole body, 3.2 W/kg head (averaged over 6 min)
    return {
        "whole_body": round(whole_body_sar, 2),
        "head": round(head_sar, 2),
        "limit_whole_body": 3.0,
        "limit_head": 3.2,
        "exceeds_limit": whole_body_sar > 3.0 or head_sar > 3.2,
    }

if __name__ == "__main__":
    print("Available presets:")
    print("-" * 50)
    for name, params in PRESETS.items():
        print(f"\n{name}:")
        print(f"  {params['description']}")
        print(f"  Sequence: {params['sequence']}, TR={params['TR']}, TE={params['TE']}")
    
    print("\n\nSAR estimates:")
    print("-" * 50)
    test_cases = [
        ("SE: FA=90, TR=500", 90, 500, "SE"),
        ("SE: FA=90, TR=200", 90, 200, "SE"),
        ("GRE: FA=60, TR=25", 60, 25, "GRE"),
        ("IR: FA=90, TR=9000", 90, 9000, "IR"),
        ("GRE: FA=90, TR=5 (high SAR)", 90, 5, "GRE"),
    ]
    for label, fa, tr, seq in test_cases:
        sar = estimate_sar(fa, tr, sequence=seq)
        warning = " ⚠️ EXCEEDS LIMIT" if sar["exceeds_limit"] else ""
        print(f"  {label}: body={sar['whole_body']:.1f} W/kg, head={sar['head']:.1f} W/kg{warning}")