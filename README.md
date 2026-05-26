# MRI Simulator

An MRI physics simulation platform written in Python. Models the signal chain from tissue properties and pulse-sequence parameters through k-space acquisition to reconstructed image, covering the major contrast mechanisms and artifacts seen in clinical MRI.

## Interactive simulator

```bash
python src/app_qt.py
```

The PyQt6 app drives the physics engine in real time:

- **Sequences** — Spin Echo, FSE/TSE (EPG echo train), Gradient Echo, Inversion Recovery, Diffusion (DWI with ADC/FA maps), MR Angiography (TOF / Phase Contrast), fMRI BOLD, and Quantitative (qMRI) parameter mapping
- **qMRI maps** — T1 (variable flip angle), T2 and T2\* (multi-echo), and Synthetic SE contrast rendered from the maps
- **Contrast & field strength** — measured 1.5T / 3T tissue tables, Gadolinium dosing, magnetization transfer, B1+ inhomogeneity, and automatic fat-water in-/opposed-phase (India-ink) for gradient echo
- **Acquisition** — matrix, FOV, bandwidth, NEX, partial Fourier, k-space apodisation, and parallel imaging (SENSE / GRAPPA / compressed sensing)
- **Artifacts** — motion ghosting, chemical shift, susceptibility dropout, zipper
- **Analysis & display** — signal/contrast curves, image histogram, live k-space, pulse-sequence diagrams, tissue-label overlays, multi-slice grids, graphic FOV/slice planning, clinical protocol presets, and SNR / CNR / SAR / scan-time metrics

> `src/app.py` is an earlier matplotlib/Tkinter prototype, retained only for reference and missing most of the above. Use `app_qt.py`.

## Physics library

All physics lives in tested, importable modules under `src/`; the GUI is a layer over them. Items tagged **(library-only)** are fully usable from Python and covered by tests, but are not yet wired into the GUI.

### Signal physics
- **Spin Echo, Gradient Echo, Inversion Recovery** — closed-form signal equations with T1/T2/PD weighting
- **Fast Spin Echo (FSE/TSE)** — full Extended Phase Graph (EPG) echo-train simulation; handles stimulated echoes and variable flip angles
- **fMRI BOLD** — T2\* modulation via neurovascular coupling, block-design t-statistic maps
- **Diffusion (DWI/DTI)** — mono-exponential and tensor-based signal, ADC/FA maps
- **MR Angiography** — Time-of-Flight inflow enhancement, Phase Contrast velocity encoding

### Advanced contrast
- **Quantitative MRI** — VFA T1 mapping (Fram linearisation), multi-echo T2/T2\* log-linear fitting, IR T1 curve fitting, synthetic contrast generation
- **Dixon fat-water** — two-point (magnitude) and three-point (B0-corrected complex) separation with fat-fraction maps; STIR fat suppression
- **Magnetization Transfer (MT)** — two-pool binary spin-bath model (Henkelman 1993); MTR maps and Z-spectra
- **B1+ inhomogeneity** — Gaussian and sinusoidal transmit field maps; double-angle and AFI B1 mapping sequences

### K-space and acquisition
- **K-space pipeline** — FFT/IFFT, matrix cropping, zero-fill interpolation, Hamming/Hanning/Blackman apodisation, partial Fourier
- **EPI** *(library-only)* — alternating-readout trajectory, Nyquist (N/2) ghosting, B0 phase-encode distortion, T2\* blurring, phase correction
- **Parallel imaging** — full Cartesian SENSE unfolding (physics-correct g-factor), approximate GRAPPA, variable-density compressed sensing

### Field and hardware effects
- **B0 field maps** *(library-only)* — dipole convolution from susceptibility labels, polynomial shim residuals, Gaussian localised distortions
- **Coil sensitivity** *(library-only)* — head-array simulation, sum-of-squares combination, g-factor maps
- **Rician noise** — correct magnitude-image noise model, SNR estimation, bias correction
- **Partial volume effects** *(library-only)* — sub-voxel tissue mixing

### Geometry and output
- **Oblique slices** — double-oblique prescription, multi-slice slabs, anisotropic voxel spacing
- **Scan geometry** — FOV, matrix, resolution, phase-encode direction, 3-plane localizer overlays
- **Artifacts** — motion ghosting, chemical shift displacement, susceptibility signal loss, zipper
- **Pulse sequence diagrams** — SE, GRE, IR, FSE, EPI, DWI, GRE-EPI renderers
- **Export** — PNG/PDF report export; DICOM export *(library-only)*

## Installation

```bash
git clone https://github.com/ea1188-commits/mrisim.git
cd mrisim
pip install -r requirements.txt
```

Python 3.11+ is required (uses `X | Y` union type syntax). No external datasets are needed: when no BrainWeb/atlas cache is present, a synthetic brain (and synthetic body regions) is generated automatically on first run.

## Running tests

```bash
python3.11 -m pytest tests/
```

1635 tests, all passing. Coverage is 97%+ across all non-GUI modules.

## Project layout

```
src/                  # all source modules (plain imports by bare name)
  app_qt.py           # PyQt6 interactive GUI
  rendering.py        # Qt-free signal-rendering helpers (tested)
  signal_engine.py    # SE / GRE / IR signal equations, SNR, scan time
  simulate.py         # thin orchestration layer
  phantom.py          # 2-D brain phantom (labels 0–4)
  phantom3d.py        # 3-D synthetic brain (labels 0–5)
  body_phantoms.py    # synthetic abdomen / knee / spine / pelvis
  tissue_db.py        # measured tissue properties at 1.5T and 3T
  kspace.py           # k-space acquisition pipeline
  epi.py              # EPI trajectory and artifacts
  fse.py              # FSE/EPG echo-train simulation
  acceleration.py     # SENSE / GRAPPA / compressed sensing
  coil.py             # coil sensitivity models
  dixon.py            # fat-water separation and STIR
  mt.py               # magnetization transfer
  b0.py               # B0 field maps and distortion
  b1.py               # B1+ inhomogeneity
  diffusion.py        # DWI / DTI
  fmri.py             # BOLD fMRI
  qmri.py             # quantitative MRI parameter mapping
  rician.py           # Rician noise model
  oblique.py          # oblique slice prescription
  scan_geometry.py    # slice prescription + 3-plane localizer geometry
  artifacts.py        # motion, chemical shift, susceptibility, zipper
  pv.py               # partial volume effects
  angiography.py      # TOF and phase-contrast MRA
  dicom_export.py     # DICOM export
  ...
tests/                # pytest suite (one file per module)
data/                 # optional phantom/atlas cache (generated; not in the repo)
```

## Physics references

- Henkelman et al. (1993) *MRM* 29:759 — two-pool MT model  
- Fram et al. (1987) *MRM* 4:306 — VFA T1 linearisation  
- Glover (1991) *J Magn Reson Imaging* 1:521 — three-point Dixon  
- Pruessmann et al. (1999) *MRM* 42:952 — SENSE reconstruction  
- Weigel (2015) *J Magn Reson Imaging* 41:266 — EPG formalism
