# Course quiz image wishlist (owner-supplied)

Ten course questions would be stronger with a real clinical image. Each slot below names the image type
and the finding that must be clearly, unambiguously visible. Get a clean, textbook example that **you own
or that is genuinely license-free** (public domain). Until an image arrives, the concept stays as its
current text-only question, so the course is always shippable.

## How to add a supplied image

1. Give me the image file (or drop it at `web/img/course-quiz/<target filename>`).
2. I resize it to <=600px wide (JPEG q85) if needed and place it at the target filename.
3. I set the question's `credit`:
   - your own image -> `{"author": "MRISim", "license": "Owner-Original", "title": "<short description>"}`
     (no source link, no attribution caption shown).
   - a genuine public-domain image -> `{"author": "<source>", "license": "Public-Domain", "source_url": "<url>", "title": "..."}`
     (a small attribution caption is shown).
4. For an **upgrade** slot I add `img` + `credit` to the existing question row; for a **new** slot I add the
   drafted question (below) to `data/course_content.json`.
5. I confirm the image genuinely shows the finding the answer asserts, dump the content byte-stable, reseed
   the Supabase `course_content` row, and run the guards. The question then goes live.

## The slots

| # | Concept / topic | Image type | Must clearly show | Target file | Wiring |
|---|---|---|---|---|---|
| 1 | Acute infarct · pathology | Axial brain DWI (b~1000), matched ADC if available | Focal bright restricted-diffusion lesion (dark on ADC) | `cq-infarct-dwi-01.jpg` | upgrade ord 914 |
| 2 | Enhancing tumor · pathology | Axial post-contrast T1 brain | Mass with abnormal ring or solid enhancement | `cq-tumor-postgad-01.jpg` | upgrade ord 916 |
| 3 | Hemorrhage / microbleeds · pathology | Axial SWI or GRE brain | Focal dark blooming signal dropout from blood products | `cq-hemorrhage-swi-01.jpg` | upgrade ord 915 |
| 4 | Multiple sclerosis · pathology | Axial or sagittal FLAIR brain | Periventricular white-matter plaques (Dawson's fingers) | `cq-ms-flair-01.jpg` | NEW question |
| 5 | Fat suppression OFF · fat-suppression | T1/PD MSK, orbit, or neck, no fat-sat | Bright subcutaneous and marrow fat | `cq-fatsat-off-01.jpg` | upgrade ord 912 |
| 6 | Fat suppression ON · fat-suppression | Same region/sequence with fat-sat (STIR ok), matched to #5 | That same fat now dark | `cq-fatsat-on-01.jpg` | upgrade ord 913 |
| 7 | Motion / flow ghosting · flow-artifacts | Any sequence with real ghosting | Discrete repeating ghosts along the phase-encode axis | `cq-ghosting-01.jpg` | upgrade ord 910 |
| 8 | Chemical shift artifact · image-quality | GRE or high-field at a fat-water border | Dark/bright misregistration band at a fat-water interface | `cq-chemshift-01.jpg` | NEW question |
| 9 | Gibbs / truncation · image-quality | T2 sagittal spine (classic) or brain | Parallel ripple lines near a sharp high-contrast border | `cq-gibbs-01.jpg` | NEW question |
| 10 | Aliasing / wrap-around · image-quality | Any image with FOV too small | Anatomy wrapped from one edge onto the other | `cq-aliasing-01.jpg` | NEW question |

"upgrade ord N" = the concept already exists as a text question; the image just gets added to that row.
"NEW question" = the full question is drafted below and gets added when its image arrives.

## Drafted NEW questions (ready to drop in)

Answer is index 0 (course.js shuffles at render). Option lengths are balanced for the answer-length guard.

### #4 Multiple sclerosis (topic: pathology) - file `cq-ms-flair-01.jpg`

```json
{
  "prompt": "This axial FLAIR image of the brain shows multiple ovoid white-matter lesions arranged perpendicular to the ventricles. In the right clinical setting, what do these most likely represent?",
  "options": [
    "Demyelinating plaques of multiple sclerosis, which are typically periventricular and bright on a FLAIR sequence",
    "Normal enlarged perivascular spaces, which always follow cerebrospinal fluid signal and suppress on every sequence",
    "Acute cortical infarcts that are confined strictly to the gray matter of the cortex",
    "Calcifications, which characteristically bloom and darken on a standard FLAIR sequence"
  ],
  "answer": 0,
  "explain": "Multiple sclerosis plaques are foci of demyelination that appear as bright ovoid white-matter lesions on FLAIR, classically periventricular and oriented perpendicular to the ventricles (Dawson's fingers). FLAIR suppresses cerebrospinal fluid so periventricular lesions stand out. Perivascular spaces follow fluid and suppress on FLAIR, infarcts are not confined to white matter, and calcification is better shown on susceptibility imaging."
}
```

### #8 Chemical shift artifact (topic: image-quality) - file `cq-chemshift-01.jpg`

```json
{
  "prompt": "This image shows a dark and a bright band at the border between a kidney and the surrounding fat, misregistered along the frequency-encoding direction. What artifact does this represent?",
  "options": [
    "Chemical shift artifact, from the small frequency difference between fat and water protons shifting fat signal along the readout axis",
    "Aliasing artifact, caused by a field of view smaller than the imaged anatomy so tissue wraps onto the opposite side of the image",
    "Zipper artifact, produced by stray radiofrequency energy leaking into the scan room during acquisition",
    "Patient motion, which spreads discrete ghost copies along the phase-encoding direction"
  ],
  "answer": 0,
  "explain": "Fat and water protons precess at slightly different frequencies, so the scanner mismaps fat signal along the frequency-encoding (readout) direction, producing a dark and bright band at fat-water interfaces such as the kidney border. It worsens at higher field strength and lower readout bandwidth. Aliasing, zipper, and motion artifacts have distinct causes and appearances."
}
```

### #9 Gibbs / truncation artifact (topic: image-quality) - file `cq-gibbs-01.jpg`

```json
{
  "prompt": "This sagittal T2 image of the spine shows several thin parallel lines running alongside the high-contrast border of the spinal cord, mimicking a syrinx. What artifact is this?",
  "options": [
    "Gibbs (truncation) artifact, from finite sampling of high spatial frequencies at a sharp signal boundary",
    "A true syrinx, which is a fluid-filled cavity within the cord that must always be surgically drained without delay",
    "Flow artifact from pulsating cerebrospinal fluid moving through the spinal canal during the acquisition",
    "Magnetic susceptibility from spinal hardware placed far outside the imaged field of view"
  ],
  "answer": 0,
  "explain": "Gibbs, or truncation, artifact arises because k-space is sampled over a finite extent, so sharp high-contrast borders such as the cord and cerebrospinal fluid interface are reconstructed with parallel ripple lines. These can mimic a cord syrinx but follow the border and change with matrix size. Increasing the acquisition matrix reduces it."
}
```

### #10 Aliasing / wrap-around (topic: image-quality) - file `cq-aliasing-01.jpg`

```json
{
  "prompt": "This image was acquired with a field of view smaller than the body part, and tissue from one edge appears overlapped onto the opposite side. What is this artifact and its cause?",
  "options": [
    "Aliasing (wrap-around), because anatomy outside the field of view is undersampled and mapped back onto the opposite side of the image",
    "Chemical shift, because fat and water protons resonate at slightly different frequencies and their signals misregister along the readout axis",
    "Gibbs artifact, because high spatial frequencies are truncated at a sharp signal boundary",
    "Gradient nonlinearity, because the gradient fields grow weaker toward the edges of the magnet bore"
  ],
  "answer": 0,
  "explain": "Aliasing, or wrap-around, occurs when the field of view is smaller than the imaged anatomy, so signal from outside the field of view is undersampled and folds back onto the opposite side of the image, usually along the phase-encoding direction. Enlarging the field of view, using phase oversampling, or applying a saturation band corrects it."
}
```
