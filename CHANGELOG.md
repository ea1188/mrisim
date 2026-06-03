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
