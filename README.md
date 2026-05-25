# mrisim

An MRI physics simulation platform written in Python. Models the signal chain from tissue properties and pulse sequence parameters through k-space acquisition to reconstructed image, covering the major contrast mechanisms and artifacts seen in clinical MRI.

## Features

### Signal physics
- **Spin Echo, Gradient Echo, Inversion Recovery** — closed-form signal equations with T1/T2/PD weighting
- **Fast Spin Echo (FSE/TSE)** — full Extended Phase Graph (EPG) echo-train simulation; handles stimulated echoes and variable flip angles
- **fMRI BOLD** — T2\* modulation via neurovascular coupling, block-design t-statistic maps
- **Diffusion (DWI/DTI)** — mono-exponential and tensor-based signal, ADC/FA maps
- **MR Angiography** — Time-of-Flight inflow enhancement, Phase Contrast velocity encoding

### Advanced contrast
- **Dixon fat-water separation** — two-point (magnitude) and three-point (B0-corrected complex) Dixon with fat fraction maps; STIR fat suppression
- **Magnetization Transfer (MT)** — two-pool binary spin-bath model (Henkelman 1993); MTR maps and Z-spectra
- **B1+ inhomogeneity** — Gaussian and sinusoidal transmit field maps; double-angle and AFI B1 mapping sequences
- **Quantitative MRI** — VFA T1 mapping (Fram linearisation), multi-echo T2/T2\* log-linear fitting, IR T1 curve fitting, synthetic contrast generation

### K-space and acquisition
- **K-space pipeline** — FFT/IFFT, matrix cropping, zero-fill interpolation, Hamming/Hanning/Blackman apodisation, partial Fourier
- **EPI** — alternating-readout trajectory, Nyquist (N/2) ghosting, B0 phase-encode distortion, T2\* blurring, phase correction
- **Parallel imaging** — full Cartesian SENSE unfolding (physics-correct g-factor), approximate GRAPPA, variable-density compressed sensing

### Field and hardware effects
- **B0 field maps** — dipole convolution from susceptibility labels, polynomial shim residuals, Gaussian localised distortions
- **Coil sensitivity** — head array simulation, sum-of-squares combination, g-factor maps
- **Rician noise** — correct magnitude-image noise model, SNR estimation, bias correction
- **Artifacts** — motion ghosting, chemical shift displacement, susceptibility signal loss, zipper artifact
- **Partial volume effects** — sub-voxel tissue mixing

### Geometry and display
- **Oblique slices** — double-oblique prescription, multi-slice slabs, anisotropic voxel spacing
- **Scan geometry** — FOV, matrix, resolution, phase-encode direction
- **Pulse sequence diagrams** — SE, GRE, IR, FSE, EPI, DWI, GRE-EPI renderers
- **DICOM export**, PNG/PDF report export

## Installation

```bash
git clone https://github.com/ea1188-commits/mrisim.git
cd mrisim
pip install numpy scipy matplotlib pyqt6 pydicom
```

Python 3.11+ is required (uses `X | Y` union type syntax).

## Running the GUI

```bash
python src/app_qt.py   # PyQt6 interface
python src/app.py      # matplotlib-based interface
```

## Running tests

```bash
python3.11 -m pytest tests/
```

1532 tests, all passing. Coverage is 97%+ across all non-GUI modules.

## Project layout

```
src/                  # all source modules (plain imports by bare name)
  signal_engine.py    # SE / GRE / IR signal equations, SNR, scan time
  simulate.py         # thin orchestration layer
  phantom.py          # 2-D brain phantom (labels 0–4)
  phantom3d.py        # 3-D synthetic brain (labels 0–5)
  tissue_db.py        # tissue properties at 1.5T and 3T
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
  artifacts.py        # motion, chemical shift, susceptibility, zipper
  pv.py               # partial volume effects
  angiography.py      # TOF and phase-contrast MRA
  ...
tests/                # pytest suite (one file per module)
data/                 # BrainWeb phantom cache (.npy)
```

## Physics references

- Henkelman et al. (1993) *MRM* 29:759 — two-pool MT model  
- Fram et al. (1987) *MRM* 4:306 — VFA T1 linearisation  
- Glover (1991) *J Magn Reson Imaging* 1:521 — three-point Dixon  
- Pruessmann et al. (1999) *MRM* 42:952 — SENSE reconstruction  
- Weigel (2015) *J Magn Reson Imaging* 41:266 — EPG formalism
