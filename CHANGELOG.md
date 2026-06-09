# Changelog

All notable changes to MRISim are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project uses
[Semantic Versioning](https://semver.org/).

**Versioning policy:** released tags are immutable. New work lands on `main` and
is published under a *new* version — a patch bump (`x.y.Z`) for fixes, tooling
and docs, a minor bump (`x.Y.0`) for new features. (Earlier in development the
`v1.0.0` tag was re-pointed as the app evolved; from `v1.0.1` onward tags are
frozen.)

## [Unreleased]

### Fixed
- **"Label the anatomy" now points at the right structure.** Names were placed at
  each tissue's centroid, which for ring/ribbon shapes (skull, scalp, cortex) falls
  *outside* the tissue — so "Skull" and "Muscle" landed in the middle of the brain.
  Each label is now anchored at the most interior point of the structure (the
  distance-transform peak), which is guaranteed to sit on the tissue.

### Added
- **Brain abscess demo pathology** — a two-part lesion with the classic triad: a
  pus core that restricts diffusion (bright on DWI, dark on ADC) and is bright on
  T2, inside a capsule that is **T2-hypointense (a dark ring)** yet **enhances with
  gadolinium** (a bright "ring-enhancing" rim on T1-post-contrast). The DWI-bright
  core is what distinguishes an abscess from a necrotic tumour. Adds tissue labels
  27 (core) and 28 (rim); the "Pathology → the right sequence" lesson gains an
  abscess capstone showing it needs *two* sequences.
- **Compare two pathologies side-by-side.** A/B compare now **captions each panel**
  with what it shows (e.g. "Abscess · DWI" vs "Tumour · DWI"), and guided-lesson
  steps can stage a comparison directly. New lesson "Abscess vs. tumour — the DWI
  test" puts the two next to each other: the abscess's pus core restricts diffusion
  (bright) while the tumour's necrotic core facilitates it (dark) — the single
  finding that tells these look-alike ring-enhancing masses apart.

### Changed
- **MR angiography / SWI are now instant in the browser.** The deterministic
  TOF vessel tree is precomputed (`scripts/build_brain_vessels.py`) and shipped
  as a ~50 KB index file, so the first SWI / MR-angiography render rebuilds it in
  under a millisecond instead of stalling ~1 minute building it in-browser. The
  engine falls back to building it in-process when the file is absent.

## [1.9.0] — 2026-06-08

Reach and clinical relevance: works on a touchscreen, and shows *why* each
sequence exists.

### Added
- **Demo pathologies → the right sequence** — the brain "Pathology" selector now
  offers four lesions, each revealed by a specific sequence: a **white-matter
  lesion** (T2/FLAIR), an **acute infarct** with restricted diffusion (bright on
  DWI, dark on ADC), a **microhaemorrhage** that blooms dark on SWI, and an
  **enhancing tumour** that brightens on T1 after gadolinium. Each behaviour is
  driven by the tested engine (diffusion ADC, susceptibility χ, Gd uptake) keyed
  to new tissue labels 24–26. New lesson "Pathology → the right sequence".
- **Touch support** — the image interactions (window/level, the scout localizer,
  and the ruler/ROI measure) now work with a finger on a tablet or phone (Pointer
  Events + `touch-action: none`); slice navigation uses the Slice slider on touch.

### Fixed
- The browser now syncs the engine's tissue table to the authoritative
  `tissue_db` at the selected field (as the desktop does), so the DWI/SWI paths
  use consistent properties.

## [1.8.0] — 2026-06-08

Hands-on teaching: see what goes wrong, and measure what you see.

### Added
- **Artifacts (teaching)** — the browser now exposes the artifacts the engine
  already models: **motion** (ghosting, with periodic/random/linear types),
  **chemical shift** (fat/water misregistration), and **susceptibility** (dropout
  near air/bone). Each toggle carries a plain-language fix-it hint (raise NEX /
  raise bandwidth / shorten TE or use spin echo), and a new lesson "When images
  go wrong — artifacts" walks all three.
- **Measurement tools** — an on-image **ruler** (distance in mm, calibrated to
  the region's field of view) and **ROI** (mean signal, noise SD, SNR and area).
  ROI statistics read the real signal image, not the windowed display, so the
  numbers are physically meaningful; a placed ROI stays live as you scrub slices.
  New lesson "Measuring the image — ruler, ROI & SNR" ties the ROI to the
  SNR/NEX tradeoff.

## [1.7.0] — 2026-06-08

A teaching release focused on someone **new to radiology** — naming what you see,
explaining every control in plain language, a beginner lesson track, and a demo
lesion that shows *why* MRI uses so many sequences.

### Added
- **Name the anatomy** — a "Label the anatomy" toggle draws the major structures'
  names directly on the image (largest region per tissue), as a beginner aid.
- **Plain-language help** — a clinical one-liner under the sequence picker
  ("what each sequence is for"), and plain-English tooltips on every acquisition
  control (TR/TE/TI/FA/matrix/bandwidth/NEX/slice/b-value/ETL).
- **"Start here" beginner lessons** — a reading-first lesson track for newcomers
  (*What is an MRI image?*, *Dark or bright? T1 vs T2*, *Why so many sequences?*,
  *Spot the lesion*), shown as its own section above the physics lessons. The
  steps drive the new toggles so the UI demonstrates what the text describes.
- **Demo pathology** — an "Add a lesion" toggle paints a white-matter lesion into
  the brain. By its tissue properties it is **nearly invisible on T1 but bright on
  T2/FLAIR** — the concrete payoff that motivates multi-sequence imaging. Backed
  by a new tissue (label 23, "Lesion (WM)") in the authoritative `tissue_db`.

### Fixed
- The "Label the anatomy" names are now **de-overlapped** — structures that share
  a centre (gray/white matter, CSF, the lesion inside white matter) no longer
  print on top of one another.

## [1.6.1] — 2026-06-08

Visual-quality and robustness refinements.

### Changed / Fixed
- Images now **auto-window to the foreground's robust intensity range** (1st–99th
  percentile), so every region/sequence opens well-windowed instead of dark and
  washed out (the spine T2 in particular).
- The **spine and knee textures are denoised** — they read like real MRI rather
  than salt-and-pepper speckle.
- The **lumbar-spine presets use the 320 mm SPIDER field of view** (was 380), so
  they fill the frame instead of opening zoomed-out.
- Browser engine/atlas fetches are **cache-busted per deploy**, so an updated
  (or fixed) atlas is always fetched fresh rather than served stale.

## [1.6.0] — 2026-06-07

A real lumbar spine, a more detailed knee, richer browser FOV planning, and new
tools for connecting the picture to the physics.

### Added
- **Real SPIDER lumbar Spine.** Replaces the torso-cropped TotalSegmentator spine
  with a sagittal lumbar T2 study from the **SPIDER** dataset (van der Graaf et
  al., Zenodo 10159290, CC-BY-4.0): vertebrae (cortical + marrow), intervertebral
  discs and the spinal canal (CSF + cord) individually segmented.
  `scripts/build_spider_spine.py` range-extracts one subject from the 3.7 GB
  archive (a seekable HTTP file over `zipfile`) rather than downloading it whole.
- **Cursor tissue probe** — hover the image to read the tissue and its T1/T2/PD
  under the cursor.
- **"Show the math"** — the active sequence's signal equation with the hovered
  tissue's T1/T2/PD and your TR/TE plugged in, and the resulting signal.
- **TR×TE contrast map** — the whole contrast landscape for a region's tissue
  pair (bright = high contrast), with the current protocol marked.
- **Richer browser FOV planning** — multi-slice + slice-gap prescription (with the
  real slice-cross-talk SNR penalty), a true oblique scout band, and **instant
  client-side window/level**.
- **Six more clinical presets** (47 → 53): Knee T1 FSE / bSSFP Cartilage, Spine T1
  Post-Gd / GRE-MERGE, Pelvis MR Urography, Torso DWIBS.
- **Three guided lessons** driving the new features.

### Changed / Fixed
- **Knee menisci, cruciates and tendons** now render as distinct dark
  fibrocartilage (new `Ligament/Meniscus` tissue, very short T2), instead of being
  lumped into muscle.
- Regions **open on their canonical plane** — spine and knee sagittal (their
  native acquisition), everything else axial.

## [1.5.1] — 2026-06-05

### Changed
- **Desktop app icon** is now the `logobackground.png` artwork with macOS-style
  rounded corners — the runtime window/dock/taskbar icon and the packaged
  `.app` (macOS) / `.exe` (Windows) file icon.

## [1.5.0] — 2026-06-05

Real anatomy everywhere, a much richer browser FOV-planning workflow, and the
app now wears our logo.

### Added
- **Real body & knee anatomy in the browser.** The TotalSegmentator
  Abdomen/Spine/Pelvis/Torso atlases and a real **Knee** (KneeBones3Dify,
  CC-BY-4.0) are fetched on demand in the browser — the same segmented anatomy
  the desktop uses, replacing the in-browser synthetic body.
- **Interactive FOV planning** in the browser localizer. The slice is drawn as a
  band of its true thickness (the whole slab in 3-D) with crosshairs through the
  prescribed centre; an in-plane **FOV box** (with a FOV % control) you can drag
  to resize or recentre; and **oblique angulation** by dragging the slice band
  (tilt/rot), with the band redrawn at the prescribed angle and the main image
  re-sampled obliquely. Double-click resets.
- **Desktop app icon** — the MRISim logo is now the window / dock / taskbar icon
  and the packaged `.app` (macOS) / `.exe` (Windows) file icon.

### Changed / Fixed
- **Real Knee anatomy** (KneeBones3Dify) on both desktop and browser, now bundled
  into the desktop release binaries — a frozen build previously couldn't find the
  cache and fell back to the synthetic knee.
- **Knee orientation** corrected to the radiological body-atlas convention
  (superior-up, anterior, patient-right) on web and desktop.
- Browser trunk regions render at their **native FOV** (no spurious
  magnification), and the **signal-curve graph** now fills the panel width so it
  is actually readable.

## [1.4.0] — 2026-06-04

**MRISim now runs in the browser** — the full physics engine, client-side via
Pyodide, shareable by link with no install. No desktop behaviour changed.

### Added
- **Browser build** at https://ea1188.github.io/mrisim/. The unchanged Qt-free
  engine runs in [Pyodide](https://pyodide.org/); a thin HTML/JS shell drives it
  and Python renders the image, signal curve and localizer to PNG. Covers the
  core loop (sequences, timing, field, orientation/slice, contrast toggles), **3D
  slab acquisition with any-plane reformat**, **clinical presets**, **A/B
  compare** with a SNR/CNR/scan-time delta, **window/level** drag, and a
  **3-plane FOV-planning localizer**. Real brain (fetched once) + synthetic body
  regions (generated in-browser); loading external NIfTI / real body atlases and
  DICOM export stay desktop-only.
- New `web/` static bundle, `build_web.py`, and a deploy workflow publishing to
  GitHub Pages on every `main` push.
- `web_adapter.py` (Qt-free) drives the engine for the browser; `render_overlay.py`
  and `theme_colors.py` factor the DICOM annotations / 3D badges / palette out of
  the desktop UI so the browser reuses the exact same rendering. 72 headless
  adapter tests, plus a headless-Chromium (Playwright) smoke in CI.

## [1.3.0] — 2026-06-03

True 3-D (slab) acquisition with **any-plane reformat** — acquire a slab once and
view it in any orientation — plus PACS-style slice scrolling. No 2-D physics
changed.

### Added
- **True 3-D slab acquisition** (`acquisition3d.py`, new). Unlike the 2-D path
  (which averages adjacent slices), this excites a slab and phase-encodes the
  slice (kz) direction as well, reconstructing a contiguous partition stack with
  a 3-D FFT. Models the real 3-D phenomena: through-plane (kz) resolution, kz
  partial Fourier, the imperfect-slab excitation profile (darker edge
  partitions), and the **√Nz SNR advantage** a 3-D encode has over a single 2-D
  slice. Available for Spin Echo, Gradient Echo, Inversion Recovery and Balanced
  SSFP via a **3D acquisition (slab)** checkbox with **partitions** and **kz
  Partial Fourier** controls.
- **Any-plane reformat.** A 3-D slab is acquired **once**; changing the view
  plane or slice **reformats** the stored recon block instead of re-scanning
  (re-acquiring only when the prescription actually changes). The viewport shows
  a `3D SLAB · Np` badge and a `REFORMAT ⟵ <acquired plane>` tag when the view
  differs from the acquired plane, and the metrics panel surfaces the partition
  count and the exact √Nz SNR gain.
- Quantitative 3-D validation in `tests/test_physics_validation.py`: the exact
  √(Nz·NEX) gain, a thin 3-D partition out-SNRing a 2-D slice of equal thickness,
  through-plane blur scaling as FOVz/n_kz, slab-profile edge attenuation, and kz
  partial Fourier shortening the scan by its fraction.

### Changed
- **Scrolling now steps one slice-thickness** (the wheel and arrow keys advance a
  whole slice, flipping through contiguous slices the way a PACS series does — a
  5 mm slice moves 5 voxels per detent, not 1). The slice **slider** still gives
  per-voxel control. 3-D reformat steps one partition; MRA (which ignores slice
  thickness) steps one voxel.
- **`app_qt.py` refactored** into focused mixins (theme, curves, scout, regions,
  interaction, metrics, export) over the same window class — no behaviour change,
  but the GUI is now covered by a headless smoke-test harness at ~94 %.

## [1.2.3] — 2026-06-02

### Fixed
- **Signal-vs-parameter curves now use the same tested equations as the image.**
  A GUI physics audit found the side-panel curves were computed inline and had
  drifted: Balanced SSFP, EPI and qMRI fell through to the **Inversion-Recovery**
  equation (so e.g. the bSSFP curve showed CSF *darkest* while the image is
  fluid-*bright*), and the Gradient-Echo curve used a `T2·0.6` approximation
  instead of the measured **T2\***. All curve modes (TE decay, TR recovery,
  contrast map, histogram prediction) now route through `signal_engine`, so the
  plotted curve provably tracks the picture.

### Added
- Headless GUI smoke-test harness (`tests/test_gui_smoke.py`): boots the window
  offscreen and exercises every sequence, preset, orientation, display mode and
  interaction handler — lifting `app_qt.py` from 0 % to ~72 % coverage. CI now
  installs the headless-Qt system libraries.

## [1.2.2] — 2026-06-02

A UI/UX overhaul of the interactive app plus a correctness fix to the
pulse-sequence diagrams. No physics-engine behaviour changed; the body phantoms
now display in radiological convention.

### Added
- **Anatomical orientation labels** (A/P/L/R/S/I) at the viewport edges, derived
  from the slice geometry and verified against landmarks. Shown only where they
  can be asserted safely (skipped for MRA MIPs, oblique planning and loaded
  NIfTI of unknown convention).
- **DICOM-style corner annotations** on the image — sequence + timing, region /
  plane / slice, window/level and FOV — replacing the old centered title.
- App logo (`data/logo.png`) in the header, bundled into the binaries.

### Changed
- **Visual refresh** — a clinical near-black + medical-blue theme with a single
  palette source, refined sliders/combos/buttons/scrollbars, a framed
  "scanner-console" viewport that separates the image/graph screen from the
  control chrome, and a matching matplotlib theme. Renamed the app to **MRISim**.
- **Window/level is now plain click-drag** on the image (MRA still rotates its
  MIP on left-drag; Ctrl+left window/levels there).
- **Body phantoms render in radiological convention** (patient-right on the
  viewer's left), consistent with the brain; a single orientation map now serves
  both.
- Moved **FOV Planning** and **Signal Curve** into the Sequence & Protocol panel.

### Fixed
- **Pulse-sequence diagrams are physically correct.** They were normalised to
  the full TR, so for the usual TE ≪ TR the events collapsed and reordered — the
  180° could render before the 90°, phase-encode after readout, the echo
  misplaced. Each channel now uses a local timeline (excitation → echo →
  readout) with widths scaled to the shown window and a "↻ TR" marker. Balanced
  SSFP, EPI and qMRI drew a mislabeled Spin-Echo diagram and now have correct
  ones (bSSFP: alternating ±α, fully-rewound gradients, TE≈TR/2; EPI: oscillating
  readout train; qMRI: multi-echo schematic). New `tests/test_psd.py` asserts
  event ordering on the rendered artists.
- Header/series-strip backgrounds now paint via the widget palette, so they
  render correctly on all Qt platforms.

## [1.2.1] — 2026-06-01

### Changed
- Preset dropdown is now grouped cleanly by region (Brain → Spine → Abdomen →
  Pelvis → Knee → Torso), and within each region ordered weighting →
  fluid-sensitive → post-contrast → advanced. Newer presets (post-Gd,
  in/opposed-phase, bSSFP, CHESS, radial, EPI) now sit with their region instead
  of being appended at the end.

### Fixed
- Selecting a preset now switches to the plane that study is conventionally
  acquired in (e.g. spine and knee → sagittal, torso and MRCP → coronal) instead
  of always staying axial.
- Changing region no longer left the orientation radio buttons out of sync (a
  stale label comparison meant the planning-panel radios didn't update).

## [1.2.0] — 2026-06-01

### Fixed
- **EPI geometric-distortion model no longer collapses the image.** Each EPI
  k-space line is now built from the correct ky=i row of the 2-D FT of the
  off-resonance–modulated image, instead of the 1-D FT of image row i (which
  confused an image-domain index with a k-space line index and destroyed ~95 %
  of the signal, squashing brain to a thin lens). Off-resonance now warps
  geometry in the phase-encode direction with energy conserved (Parseval), as it
  should. Resolves the v1.1.0 known issue.

### Added
- **Brain EPI T2\*** preset — single-shot GRE-EPI (the BOLD/diffusion readout):
  T2\*-weighted with bright CSF and EPI's signatures (phase-encode geometric
  stretch at the frontal sinus / ear canals, faint N/2 ghost). Previously held
  back by the distortion bug; now unblocked.
- Regression test asserting the EPI B0 model conserves signal energy (warps,
  not collapses) across a range of off-resonance levels.

## [1.1.0] — 2026-06-02

### Added
- 6 clinical presets showcasing the newer sequences/effects: Brain CISS, Torso
  Cine and Abdomen balanced SSFP; Knee and Abdomen spectral- (CHESS) fat-sat;
  and a motion-robust Abdomen radial acquisition. The preset loader now applies
  (and resets) the fat-sat and trajectory controls.

### Changed
- README refreshed to match the current engine: Balanced SSFP and EPI listed as
  selectable sequences, plus flow, spectral fat-sat, radial sampling, slice
  cross-talk and gradient-distortion features; CI and latest-release badges; a
  link to this changelog.

### Known issues
- The EPI geometric-distortion model is over-aggressive (it can collapse the
  image), so the planned Brain EPI preset was held back; EPI remains selectable
  pending a distortion-model fix.

## [1.0.1] — 2026-06-01

Quality and tooling pass — no new user-facing features.

### Added
- Physics validation suite (`tests/test_physics_validation.py`): 20
  literature-grounded assertions (Ernst angle, IR/FLAIR/STIR nulls, bSSFP
  banding location, de Bazelaire/Stanisz/Wansapura relaxation values, fat–water
  shift in Hz, diffusion law, gadolinium). The pass found no physics bugs.
- Type-checking enforced in CI: fixed all mypy errors under the strict
  `mypy.ini` config and added `mypy src/` to the workflow.
- Linting in CI: a `ruff` config that targets real problems (pyflakes + bugbear,
  not the codebase's intentional compact statement style), wired into the
  workflow.
- A single-source `__version__` shown in the window title.

### Fixed
- Divide-by-zero in the radial sampling mask; unclosed JSON file handles in
  `region_index`; 58 unused imports and assorted dead code surfaced by ruff.

## [1.0.0] — 2026-05-31

First public release: an interactive MRI physics simulator (PyQt) with
downloadable, no-Python binaries for Windows/macOS/Linux.

### Sequences
Spin Echo, FSE/TSE (full EPG echo train), spoiled Gradient Echo, Inversion
Recovery, Balanced SSFP (with off-resonance banding), Echo-Planar (EPI),
Diffusion (DWI/DTI with ADC/FA maps), MR Angiography (TOF / phase contrast),
fMRI BOLD, and quantitative (qMRI) mapping.

### Anatomy
- Bundled real BrainWeb brain phantom (works out of the box).
- Real segmented body regions — Abdomen, Spine, Pelvis and whole Torso — from the
  TotalSegmentator MRI dataset, with real-MRI texture and synthetic fallbacks;
  the four region caches are bundled so they render with no download.
- Load any TotalSegmentator NIfTI mask, or index a folder of masks by region.

### Contrast, signal & noise
1.5 T / 3 T measured relaxation tables; gadolinium enhancement (brain and body,
blood-pool weighted); magnetization transfer; B0 / B1+ inhomogeneity; partial
volume. A calibrated Rician noise model with a fixed (hardware) noise floor, so
SNR scales correctly with NEX, bandwidth, voxel volume, field strength,
acceleration (g·√R) and diffusion b-value.

### Acquisition
Matrix/resolution, field of view (magnify + wraparound when small, surround when
large), partial Fourier, parallel imaging (SENSE / GRAPPA / CS) modelled as a
successful recon with a g·√R SNR cost that NEX recovers, non-Cartesian radial
sampling with streak artifacts, imperfect slice profile and multi-slice
cross-talk, and three fat-suppression methods (STIR, Dixon, spectral CHESS).

### Flow & artifacts
Flowing-blood signal (spin-echo void / gradient-echo inflow); motion (discrete
respiratory ghosts); sub-pixel chemical shift; susceptibility dropout localised
to internal air; gradient-nonlinearity geometric distortion; zipper.

### Distribution
GitHub Actions builds standalone Windows/macOS/Linux binaries on each release and
attaches them; the BrainWeb brain and body-region caches are bundled. 1,700+
tests, CI green.
