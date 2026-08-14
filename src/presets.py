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
        "acq3d": True,
        "n_partitions": 32,
        "description": "MPRAGE (MP-RAGE): standard 3D T1w at 3T, acquired as a slab (acquire once, reformat any plane). TI=900ms maximises WM/GM contrast. WM bright, GM intermediate, CSF dark. Gold standard for cortical morphometry."
    },
    "Brain 3D FLAIR": {
        "sequence": "Inversion Recovery",
        "TR": 6000,
        "TE": 120,
        "TI": 1800,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 240,
        "bandwidth": 200,
        "NEX": 1,
        "acq3d": True,
        "n_partitions": 32,
        "description": "3D FLAIR: isotropic CSF-nulled FLAIR acquired as one slab, reformatted to any plane. Better small-lesion conspicuity (MS, cortical/juxtacortical) than 2D FLAIR, with no slice gap. CSF dark, lesions bright."
    },
    "Brain 3D T2 (SPACE)": {
        "sequence": "Spin Echo",
        "TR": 3200,
        "TE": 100,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 240,
        "bandwidth": 200,
        "NEX": 1,
        "acq3d": True,
        "n_partitions": 32,
        "description": "3D T2 (SPACE / CUBE / VISTA family): a heavily T2-weighted volumetric acquisition reformatted to any plane. Thin contiguous partitions and isotropic voxels; CSF and fluid bright. (Clinically a variable-flip 3D TSE; modelled here as a 3D spin-echo slab.)"
    },
    "Brain ASL Perfusion": {
        "sequence": "Perfusion (ASL)",
        "TR": 4000,
        "TE": 14,
        "TI": 1800,
        "flip_angle": 90,
        "matrix_size": 128,
        "FOV": 240,
        "bandwidth": 250,
        "NEX": 3,
        "perf_display": "CBF Map",
        "pld": 1800,
        "label_duration": 1800,
        "description": "Pseudo-continuous ASL CBF map — magnetically-labelled arterial blood as an endogenous tracer (no contrast). Grey-matter flow ~2.5–3× white. Stroke penumbra, tumour grade, vascular reserve. Switch Display to Perfusion-weighted to see the raw label−control difference."
    },
    "Brain DSC Perfusion": {
        "sequence": "Perfusion (Dynamic)",
        "TR": 1500,
        "TE": 30,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 128,
        "FOV": 240,
        "bandwidth": 250,
        "NEX": 1,
        "contrast_enabled": True,
        "contrast_dose": 5,
        "perf_dyn_display": "CBV (DSC)",
        "description": "Dynamic Susceptibility Contrast (DSC) — a gadolinium-bolus T2*-EPI acquisition tracked over time. The default CBV map shows grey > white blood volume; an infarct core drops CBV with prolonged MTT, while a high-grade tumour shows raised CBV. Switch the Dynamic map to CBF / MTT, or to Ktrans (DCE) for blood-brain-barrier permeability."
    },
    "Brain SWI": {
        "sequence": "Susceptibility (SWI)",
        "TR": 28,
        "TE": 20,
        "TI": 150,
        "flip_angle": 15,
        "matrix_size": 256,
        "FOV": 240,
        "bandwidth": 125,
        "NEX": 4,
        "description": "Susceptibility-weighted imaging (SWI). Long TE amplifies phase differences from iron, blood products, calcification. Microbleeds, venous blood appear dark. Real SWI is a long, averaged 3D acquisition; NEX 4 keeps the characteristic short TR / long TE while lifting SNR out of the noise."
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
    "DTI FA Map": {
        "sequence": "Diffusion (DWI)",
        "TR": 9000,
        "TE": 90,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 128,
        "FOV": 240,
        "bandwidth": 250,
        "NEX": 2,
        "b_value": 1000,
        "diff_direction": "Left-Right",
        "diff_display": "FA Map",
        "description": "Diffusion-tensor FA map. Fractional anisotropy is high (bright) in coherent white-matter tracts (corpus callosum, internal capsule) and low (dark) in isotropic CSF/grey matter — the basis of tractography."
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
        "fmri_display": "Activation Map",
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
        "fmri_display": "Activation Map",
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
    "Abdomen 3D GRE (VIBE)": {
        "sequence": "Gradient Echo",
        "TR": 4,
        "TE": 2,
        "TI": 150,
        "flip_angle": 10,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 500,
        "NEX": 1,
        "fatsat_enabled": True,
        "acq3d": True,
        "n_partitions": 32,
        "description": "3D spoiled GRE (VIBE / LAVA / THRIVE): fat-suppressed volumetric T1w acquired in one breath-hold, reformatted to any plane. The workhorse for dynamic post-contrast liver/abdomen imaging — enable Gd to see arterial/portal enhancement."
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
        "FOV": 320,
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
        "FOV": 320,
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
        "FOV": 320,
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
        "FOV": 320,
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
        "sequence": "FSE / TSE",
        "TR": 4000,
        "TE": 60,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 150,
        "bandwidth": 200,
        "NEX": 2,
        "etl": 8,
        "echo_spacing": 10,
        "fatsat_enabled": True,
        "description": "T2-weighted FSE with spectral (CHESS) fat saturation — a true 'T2 fat-sat': fat dark while fluid, joint effusion and marrow oedema stay bright. Bone contusions, stress fractures, cartilage defects, ligament tears. (Unlike STIR it leaves water untouched but fails where B0 is inhomogeneous.)"
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
        "acq3d": True,
        "n_partitions": 28,
        "description": "GRE T2* knee, acquired as a 3D slab for multi-planar reformat (MPR). Articular cartilage mapping. Sensitive to calcifications, haemosiderin, loose bodies."
    },
    "Knee PD Coronal": {
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
        "description": "PD-weighted FSE, coronal — collateral ligaments (MCL/LCL), the meniscal body and the tibiofemoral joint line."
    },
    "Knee PD FS Coronal": {
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
        "fatsat_enabled": True,
        "description": "PD-weighted FSE with spectral (CHESS) fat saturation, coronal — marrow oedema and collateral-ligament / meniscal injury against suppressed fat."
    },
    "Knee T2 FS Axial": {
        "sequence": "FSE / TSE",
        "TR": 4000,
        "TE": 60,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 150,
        "bandwidth": 200,
        "NEX": 2,
        "etl": 8,
        "echo_spacing": 10,
        "fatsat_enabled": True,
        "description": "T2-weighted FSE with spectral (CHESS) fat saturation, axial — patellofemoral cartilage, the retinacula and joint effusion; fluid-bright with marrow oedema, fat dark."
    },

    # ------------------------------------------------------------------ #
    #  Post-contrast (Gadolinium)
    # ------------------------------------------------------------------ #
    "Brain T1 Post-Gd": {
        "sequence": "Spin Echo",
        "TR": 500,
        "TE": 15,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 240,
        "bandwidth": 125,
        "NEX": 1,
        "contrast_enabled": True,
        "contrast_dose": 2,
        "description": "T1w SE after gadolinium. Enhancing tumour, abscess rim, meningeal disease and vessels brighten where the blood–brain barrier is disrupted; normal brain barely changes."
    },
    "Abdomen T1 Post-Gd": {
        "sequence": "Gradient Echo",
        "TR": 200,
        "TE": 4,
        "TI": 150,
        "flip_angle": 70,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 500,
        "NEX": 1,
        "contrast_enabled": True,
        "contrast_dose": 2,
        "description": "Post-Gd T1 GRE (VIBE). Arterial-phase enhancement of liver, spleen, kidneys and vessels. Hypervascular lesions (HCC) enhance avidly; portal/hepatic veins brighten."
    },
    "Pelvis T1 Post-Gd": {
        "sequence": "Gradient Echo",
        "TR": 220,
        "TE": 4,
        "TI": 150,
        "flip_angle": 70,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 400,
        "NEX": 1,
        "contrast_enabled": True,
        "contrast_dose": 2,
        "description": "Post-Gd T1 GRE pelvis. Tumour and nodal enhancement; bladder, prostate/uterine and iliac vessel enhancement. Pairs with pre-contrast T1 for subtraction."
    },

    # ------------------------------------------------------------------ #
    #  In/Opposed-phase (chemical-shift / Dixon, 3T)
    # ------------------------------------------------------------------ #
    "Abdomen In-Phase": {
        "sequence": "Gradient Echo",
        "TR": 200,
        "TE": 2.3,
        "TI": 150,
        "flip_angle": 70,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 500,
        "NEX": 1,
        "description": "In-phase GRE (TE≈2.3 ms at 3T): fat and water signals add. Baseline for the in/opposed-phase pair used to detect microscopic fat."
    },
    "Abdomen Opposed-Phase": {
        "sequence": "Gradient Echo",
        "TR": 200,
        "TE": 1.15,
        "TI": 150,
        "flip_angle": 70,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 500,
        "NEX": 1,
        "description": "Opposed-phase GRE (TE≈1.15 ms at 3T): fat and water cancel, giving India-ink organ borders and signal drop in fat-containing lesions (adrenal adenoma, fatty liver)."
    },

    # ------------------------------------------------------------------ #
    #  Torso  (FOV 400 mm — whole chest–abdomen–pelvis atlas)
    # ------------------------------------------------------------------ #
    "Torso T2 Coronal": {
        "sequence": "FSE / TSE",
        "TR": 4500,
        "TE": 90,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 400,
        "bandwidth": 400,
        "NEX": 1,
        "etl": 32,
        "echo_spacing": 8,
        "description": "Coronal T2w FSE survey of the whole torso. Fluid bright; large-field overview of lungs, heart, liver, spleen, kidneys and spine in one acquisition."
    },
    "Torso T1 GRE": {
        "sequence": "Gradient Echo",
        "TR": 200,
        "TE": 4,
        "TI": 150,
        "flip_angle": 70,
        "matrix_size": 256,
        "FOV": 400,
        "bandwidth": 500,
        "NEX": 1,
        "description": "T1w GRE torso. Anatomic overview with bright fat planes; useful pre-contrast baseline and for staging surveys."
    },
    "Torso STIR Coronal": {
        "sequence": "Inversion Recovery",
        "TR": 5000,
        "TE": 60,
        "TI": 265,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 400,
        "bandwidth": 300,
        "NEX": 1,
        "description": "Coronal STIR torso. Fat suppressed — sensitive whole-body screen for marrow edema, metastases, lymphadenopathy and inflammation."
    },

    # ------------------------------------------------------------------ #
    #  Balanced SSFP (bSSFP / TrueFISP / FIESTA)
    # ------------------------------------------------------------------ #
    "Brain CISS (bSSFP)": {
        "sequence": "Balanced SSFP",
        "TR": 6,
        "TE": 3,
        "TI": 150,
        "flip_angle": 55,
        "matrix_size": 256,
        "FOV": 240,
        "bandwidth": 250,
        "NEX": 1,
        "acq3d": True,
        "n_partitions": 40,
        "description": "Heavily T2/T1-weighted bSSFP (CISS/FIESTA), acquired as a thin 3D slab. Very bright CSF gives a cisternographic look — cranial nerves and the internal auditory canal stand out against bright fluid. Off-resonance banding may appear."
    },
    "Torso Cine (bSSFP)": {
        "sequence": "Balanced SSFP",
        "TR": 4,
        "TE": 2,
        "TI": 150,
        "flip_angle": 50,
        "matrix_size": 256,
        "FOV": 400,
        "bandwidth": 400,
        "NEX": 1,
        "description": "Bright-blood bSSFP (the cardiac cine workhorse). Blood and fluid are bright with high SNR per unit time; banding from off-resonance grows at longer TR / higher field."
    },
    "Abdomen bSSFP": {
        "sequence": "Balanced SSFP",
        "TR": 4,
        "TE": 2,
        "TI": 150,
        "flip_angle": 50,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 400,
        "NEX": 1,
        "description": "Single-shot bSSFP abdominal survey. Fluid-bright and motion-robust — bowel, vessels and fluid collections stand out in a fast breath-hold."
    },

    # ------------------------------------------------------------------ #
    #  Spectral fat-sat / radial — showcase the engine
    # ------------------------------------------------------------------ #
    "Knee PD Fat-Sat (CHESS)": {
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
        "fatsat_enabled": True,
        "description": "PD-weighted FSE with spectral (CHESS) fat saturation — fat dark, cartilage/fluid conspicuous. Unlike STIR it leaves water untouched, but fails where B0 is inhomogeneous."
    },
    "Abdomen T1 FS Post-Gd": {
        "sequence": "Gradient Echo",
        "TR": 200,
        "TE": 4,
        "TI": 150,
        "flip_angle": 70,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 500,
        "NEX": 1,
        "contrast_enabled": True,
        "contrast_dose": 2,
        "fatsat_enabled": True,
        "description": "Fat-suppressed (CHESS) post-Gd T1 GRE. Suppressing bright fat maximises conspicuity of enhancing organs, vessels and lesions on the arterial/portal phase."
    },
    "Abdomen Radial": {
        "sequence": "Gradient Echo",
        "TR": 200,
        "TE": 4,
        "TI": 150,
        "flip_angle": 70,
        "matrix_size": 256,
        "FOV": 380,
        "bandwidth": 500,
        "NEX": 1,
        "trajectory": "Radial",
        "radial_spokes": 96,
        "description": "Radial (non-Cartesian) GRE — the densely-sampled centre makes it motion-robust (free-breathing), while undersampled spokes reconstruct as the characteristic radial streaks."
    },

    # ------------------------------------------------------------------ #
    #  Echo-planar (EPI) — single-shot T2*, with the readout artifacts
    # ------------------------------------------------------------------ #
    "Brain EPI T2*": {
        "sequence": "Echo Planar (EPI)",
        "TR": 4000,
        "TE": 50,
        "TI": 150,
        "flip_angle": 90,
        "matrix_size": 128,
        "FOV": 240,
        "bandwidth": 1500,
        "NEX": 1,
        "epi_b0_hz": 60,
        "epi_esp": 6,
        "epi_ghost": 10,
        "epi_correct_ghost": False,
        "description": "Single-shot GRE-EPI (the BOLD/diffusion readout). T2*-weighted with bright CSF, acquired in one shot — so it carries EPI's signatures: geometric stretch in the phase-encode direction where B0 is off-resonance (frontal sinus / ear canals) and a faint N/2 (Nyquist) ghost. Turn on ghost correction to suppress the ghost."
    },

    # ------------------------------------------------------------------ #
    #  Additional region protocols (MSK / spine / body)
    # ------------------------------------------------------------------ #
    "Knee T1 FSE": {
        "sequence": "FSE / TSE", "TR": 650, "TE": 12, "TI": 150, "flip_angle": 90,
        "matrix_size": 320, "FOV": 150, "bandwidth": 200, "NEX": 1, "etl": 4,
        "description": "T1 FSE of the knee. Short TR/TE: fatty marrow and subcutaneous fat are bright, fluid is dark. Best for marrow infiltration, occult fractures and overall bone/anatomy."
    },
    "Knee bSSFP Cartilage": {
        "sequence": "Balanced SSFP", "TR": 12, "TE": 6, "TI": 150, "flip_angle": 40,
        "matrix_size": 320, "FOV": 150, "bandwidth": 350, "NEX": 2,
        "acq3d": True, "n_partitions": 32,
        "description": "3D balanced SSFP (DESS / FIESTA-C type) of the knee, acquired as an isotropic slab and reformatted to any plane. T2/T1-weighted bright fluid against intermediate cartilage gives high cartilage–fluid–bone contrast for the articular surfaces; off-resonance can band."
    },
    "Knee T2 Map (qMRI)": {
        "sequence": "Quantitative (qMRI)", "TR": 1500, "TE": 15, "TI": 150, "flip_angle": 90,
        "matrix_size": 256, "FOV": 150, "bandwidth": 200, "NEX": 1,
        "qmri_display": "T2 Map (multi-echo)",
        "description": "Quantitative T2 map of articular cartilage (multi-echo fit; pixel value = T2 in ms). Cartilage T2 rises with collagen-matrix breakdown and water content, so a focal T2 increase flags early degeneration before it is visible on morphological images."
    },
    "Spine T1 Post-Gd": {
        "sequence": "Spin Echo", "TR": 600, "TE": 12, "TI": 150, "flip_angle": 90,
        "matrix_size": 320, "FOV": 320, "bandwidth": 150, "NEX": 2,
        "contrast_enabled": True, "contrast_dose": 4,
        "description": "Post-gadolinium T1 of the spine. Enhancing tumour, infection (discitis/epidural abscess) and active inflammation brighten; compare with the pre-contrast T1 to spot true enhancement."
    },
    "Spine GRE T2* (MERGE)": {
        "sequence": "Gradient Echo", "TR": 700, "TE": 18, "TI": 150, "flip_angle": 20,
        "matrix_size": 320, "FOV": 320, "bandwidth": 200, "NEX": 1,
        "description": "Axial T2*-weighted GRE of the cord (MERGE/MEDIC-type). Bright CSF myelographic effect outlines the cord and exiting nerve roots; T2* makes haemorrhage and disc/osteophyte bloom dark."
    },
    "Pelvis MR Urography": {
        "sequence": "FSE / TSE", "TR": 8000, "TE": 800, "TI": 150, "flip_angle": 90,
        "matrix_size": 256, "FOV": 380, "bandwidth": 250, "NEX": 1, "etl": 160,
        "description": "Heavily T2-weighted (very long TE) coronal slab — only near-static fluid stays bright, so urine in the collecting systems, ureters and bladder lights up like a urogram while everything else darkens (the same trick as MRCP)."
    },
    "Torso DWIBS": {
        "sequence": "Diffusion (DWI)", "TR": 4000, "TE": 70, "TI": 150, "flip_angle": 90,
        "matrix_size": 128, "FOV": 400, "bandwidth": 1500, "NEX": 2, "b_value": 800,
        "fatsat_enabled": True,
        "description": "Diffusion-weighted whole-body imaging with background suppression. Fat-suppressed high-b diffusion leaves restricted tissue — nodes, cellular tumour — bright on a dark background; read alongside the ADC map to confirm true restriction."
    },
    "Cardiac LGE": {
        "sequence": "Inversion Recovery", "TR": 700, "TE": 3, "TI": 300, "flip_angle": 25,
        "matrix_size": 256, "FOV": 360, "bandwidth": 250, "NEX": 1,
        "contrast_enabled": True, "contrast_dose": 4,
        "description": "Late gadolinium enhancement (LGE): an inversion-recovery T1w acquired ~10 min post-contrast with TI set to null normal myocardium (dark). Scar / fibrosis / infarct retains contrast and stays bright — the reference standard for myocardial viability."
    },
}

_REGION_PREFIXES: list[tuple[str, str]] = [
    ("Abdomen", "Abdomen"), ("Spine", "Spine"), ("Pelvis", "Pelvis"),
    ("Knee", "Knee"), ("Torso", "Torso"), ("Brain", "Brain"), ("MRCP", "Abdomen"),
    ("DWI", "Brain"), ("ADC", "Brain"), ("TOF", "Brain"), ("fMRI", "Brain"),
    ("DTI", "Brain"), ("Cardiac", "Torso"),
]


def get_preset_region(name: str) -> str | None:
    """Return the anatomy region for a preset, or None if unknown."""
    for prefix, region in _REGION_PREFIXES:
        if name.startswith(prefix):
            return region
    return None


# Acquisition plane per preset. Anything not listed defaults to axial — the most
# common acquisition plane — so only the presets conventionally acquired in
# another plane are named here. Selecting a preset then also picks the plane it
# is normally read in (e.g. spine sagittal, knee sagittal, torso coronal).
_PRESET_PLANE: dict[str, str] = {
    "Brain MPRAGE": "sagittal",            # 3-D IR-GRE, acquired sagittal
    "Brain 3D FLAIR": "sagittal",          # 3-D, reformats to any plane
    "Brain 3D T2 (SPACE)": "sagittal",     # 3-D, reformats to any plane
    "Knee T2 Map (qMRI)": "sagittal",
    "Cardiac LGE": "coronal",
    "Spine T1 Sagittal": "sagittal",
    "Spine T2 Sagittal": "sagittal",
    "Spine STIR": "sagittal",
    "Spine Axial T2": "axial",
    "Knee PD FSE": "sagittal",
    "Knee T2 Fat-Sat": "sagittal",
    "Knee GRE T2*": "sagittal",
    "Knee PD Fat-Sat (CHESS)": "sagittal",
    "Knee PD Coronal": "coronal",
    "Knee PD FS Coronal": "coronal",
    "Knee T2 FS Axial": "axial",
    "Knee T1 FSE": "sagittal",
    "Knee bSSFP Cartilage": "sagittal",
    "Spine T1 Post-Gd": "sagittal",
    "Spine GRE T2* (MERGE)": "axial",
    "Pelvis MR Urography": "coronal",
    "Torso DWIBS": "coronal",
    "Torso T2 Coronal": "coronal",
    "Torso T1 GRE": "coronal",
    "Torso STIR Coronal": "coronal",
    "Torso Cine (bSSFP)": "coronal",
    "MRCP": "coronal",                     # coronal thick-slab over the biliary tree
}


def get_preset_plane(name: str) -> str:
    """Acquisition plane for a preset: 'axial', 'sagittal' or 'coronal'."""
    return _PRESET_PLANE.get(name, "axial")


# Dropdown display order: grouped by region, and within each region ordered
# weighting → fluid-sensitive → post-contrast → advanced. Any preset not listed
# here is appended in definition order, so a newly added preset still appears.
_PRESET_ORDER: list[str] = [
    # Brain — structural
    "Brain T1 SE", "Brain T2 SE", "Brain PD", "Brain FLAIR", "Brain STIR",
    "Brain MPRAGE", "Brain 3D FLAIR", "Brain 3D T2 (SPACE)",
    "Brain SWI", "Brain GRE T2*", "Brain GRE T1",
    "Brain T1 Post-Gd", "Brain CISS (bSSFP)", "Brain EPI T2*",
    # Brain — diffusion / function / angiography
    "DWI Stroke", "DWI High-b", "ADC Map", "DTI FA Map",
    "Brain ASL Perfusion", "Brain DSC Perfusion",
    "fMRI BOLD Standard", "fMRI High Resolution",
    "TOF MRA Circle of Willis", "TOF MRA Thin Slab",
    # Spine
    "Spine T1 Sagittal", "Spine T2 Sagittal", "Spine STIR", "Spine Axial T2",
    "Spine T1 Post-Gd", "Spine GRE T2* (MERGE)",
    # Abdomen
    "Abdomen T1 GRE", "Abdomen 3D GRE (VIBE)", "Abdomen T2 FSE", "Abdomen STIR",
    "Abdomen In-Phase", "Abdomen Opposed-Phase", "Abdomen DWI",
    "Abdomen T1 Post-Gd", "Abdomen T1 FS Post-Gd",
    "Abdomen bSSFP", "Abdomen Radial", "MRCP",
    # Pelvis
    "Pelvis T1 SE", "Pelvis T2 High-Res", "Pelvis STIR", "Pelvis DWI",
    "Pelvis T1 Post-Gd", "Pelvis MR Urography",
    # Knee
    "Knee PD FSE", "Knee PD Coronal", "Knee T1 FSE",
    "Knee T2 Fat-Sat", "Knee PD Fat-Sat (CHESS)", "Knee PD FS Coronal", "Knee T2 FS Axial",
    "Knee GRE T2*", "Knee bSSFP Cartilage", "Knee T2 Map (qMRI)",
    # Torso
    "Torso T2 Coronal", "Torso T1 GRE", "Torso STIR Coronal", "Torso Cine (bSSFP)",
    "Torso DWIBS", "Cardiac LGE",
]


def get_preset_names() -> list[str]:
    """Preset names in grouped display order (any unlisted appended last)."""
    ordered = [n for n in _PRESET_ORDER if n in PRESETS]
    extra = [n for n in PRESETS if n not in _PRESET_ORDER]
    return ordered + extra


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