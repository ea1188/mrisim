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
