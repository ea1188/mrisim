# Headless API — scripting MRISim without the GUI

MRISim's simulation engine is **Qt-free**. `src/simulator.py` holds the whole
acquisition pipeline as a plain class: you give it a label volume plus a
parameter dict and it returns `(image, metrics)`. Nothing imports PyQt or opens
a window, so the engine runs in a script, a notebook, a test, or on a headless
server — this is the project's preferred surface for research use.

`examples/headless_demo.py` is a complete, runnable reference (sequence
comparison, a TE sweep, and a quantitative map). This document is the contract
behind it.

## Quick start

```python
import sys, os
sys.path.insert(0, "src")                 # modules import each other by bare name

import simulator
from brainweb_loader import get_brainweb_or_synthetic

volume, source = get_brainweb_or_synthetic()   # (Z, Y, X) integer label volume

sim = simulator.Simulator()
sim.volume = volume
sim.native_fov = 220.0                    # field of view of the volume, mm
sim.orientation = "axial"                 # "axial" | "coronal" | "sagittal"
sim.slice_idx = volume.shape[0] // 2

params = simulator.default_params(sequence="Spin Echo", TR=4000, TE=100)  # T2w
image, metrics = sim.simulate(params)

print(image.shape, metrics["snr_wm"], metrics["scan_time"])
```

`image` is a 2-D `float` NumPy array (display-scaled). `metrics` is the dict
described below.

## The three moving parts

### 1. The volume

A 3-D integer **label** array with axis convention `axis0=Z, axis1=Y, axis2=X`
(matching `phantom3d.get_slice`). Each integer is a tissue code resolved through
`tissue_db`. Ways to get one:

- `brainweb_loader.get_brainweb_or_synthetic()` — the real BrainWeb brain if the
  phantom is present, else a synthetic brain. Returns `(volume, source_label)`.
- `body_phantoms.build_region(name)` / `nifti_region.load_region(name)` — body
  regions (Abdomen, Pelvis, Torso, Knee, Spine), real atlas if bundled.
- Any label volume you construct yourself, as long as its codes exist in
  `tissue_db`.

Optional companion volumes are set as attributes for the sequences that need
them: `sim.vessels` (MRA), `sim.activation` (fMRI), `sim.texture` (real-MRI
detail modulation for body regions). Leave them `None` otherwise.

### 2. View / geometry state (attributes on `sim`)

Set before calling `simulate()`:

| attribute | meaning |
|---|---|
| `orientation` | `"axial"`, `"coronal"`, or `"sagittal"` |
| `slice_idx` | slice index into the oriented volume |
| `native_fov` | volume field of view in mm (drives resolution/SNR scaling) |
| `tilt`, `rot` | oblique angles in degrees (with `fov_planning=True`) |
| `fov_planning` | enable in-plane FOV box + oblique prescription |
| `inplane_fov_pct`, `inplane_off` | in-plane FOV size / offset when planning |
| `no_phase_wrap`, `pe_swap` | phase oversampling / swap phase-encode direction |
| `satband_*` | saturation-band position/width/angle |

`sim.get_max_slice_idx()` returns the valid `slice_idx` range for the current
orientation.

### 3. The parameter dict

`simulator.default_params(**overrides)` returns a complete, valid params dict —
override any subset. It mirrors exactly what the GUI assembles from its controls,
so a scripted run and a GUI run with the same params produce the same image. Key
fields (see the function for the full set):

- **Contrast:** `sequence`, `TR`, `TE`, `TI`, `flip_angle`
- **Sampling:** `matrix_size`, `FOV`, `fov_fraction`, `bandwidth`, `NEX`,
  `slice_thickness`, `n_slices`
- **Acceleration:** `accel_factor`, `accel_method` (`"SENSE"`/`"GRAPPA"`/`"CS"`),
  `pf_enabled`, `pf_fraction`, `trajectory`, `radial_spokes`
- **Sequence-specific:** diffusion (`b_value`, `diff_display`), angiography
  (`angio_type`, `venc`, …), fMRI (`fmri_display`, …), qMRI (`qmri_display`),
  perfusion (`perf_display`, `perf_dyn_display`, `pld`, …)
- **Field / hardware / artifacts:** `field_strength`, `contrast_enabled`,
  `motion_enabled`, `susceptibility_enabled`, `b1_inhom_enabled`, `mt_enabled`, …

`sequence` accepts: `"Spin Echo"`, `"FSE / TSE"`, `"Gradient Echo"`,
`"Inversion Recovery"`, `"Balanced SSFP"`, `"Echo Planar (EPI)"`,
`"Diffusion (DWI)"`, `"MR Angiography"`, `"fMRI (BOLD)"`,
`"Quantitative (qMRI)"`, `"Perfusion (ASL)"`, `"Perfusion (Dynamic)"`.

## The metrics dict

`simulate()` returns `(image, metrics)`. `metrics` always contains:

| key | meaning |
|---|---|
| `scan_time` | acquisition time in **seconds** |
| `resolution` | in-plane voxel size in mm (`FOV / matrix`) |
| `snr_wm`, `snr_gm` | measured SNR in white/grey matter (0 for parameter maps) |
| `snr` | overall SNR estimate |
| `snr_eff` | SNR per √minute — the time-normalised efficiency figure |
| `sar_head` | estimated head SAR in W/kg |
| `sar_exceeds` | `True` if `sar_head` exceeds the 3.2 W/kg first-level limit |
| `g_factor` | parallel-imaging noise-amplification factor |
| `noise_sigma` | fitted noise σ (image acquisitions only) |

For parameter-map outputs (qMRI, ADC/FA, activation/T-stat, CBF, DSC/DCE, MRA
MIP) the SNR fields are 0 — the pixel values *are* the quantity, not a weighted
image. After a call, `sim.last_kspace` holds the acquired k-space.

## 3-D slab acquisition

Set `params["acq3d"] = True` for the sequences that support it to run a true 3-D
slab acquisition + reconstruction; the reconstructed slab is cached on
`sim._recon3d` so subsequent orientation changes reformat rather than re-scan.

## Reproducibility

Runs are deterministic: noise and motion draw from seeds derived from the slice
index and orientation, so the same volume + params + view state give a
bit-identical image every time — important for tests and for citable results.

## See also

- `examples/headless_demo.py` — runnable end-to-end script
- `docs/VALIDATION.md` — how simulated values are benchmarked against literature
- `scripts/validation_report.py` — the validation harness (a headless-API client)
