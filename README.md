<h1>MRISim</h1>
<p><b>An interactive MRI physics simulator</b> — from tissue &amp; pulse-sequence parameters through k-space to the reconstructed image, in real time.</p>

[![CI](https://github.com/ea1188/mrisim/actions/workflows/ci.yml/badge.svg)](https://github.com/ea1188/mrisim/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/ea1188/mrisim)](https://github.com/ea1188/mrisim/releases/latest)
[![License: MIT](https://img.shields.io/github/license/ea1188/mrisim?color=blue)](LICENSE)
![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-444d56)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)

</div>

  <img src="docs/demo.gif" width="840" alt="MRISim — sweeping echo time (TE) on a spin-echo brain: contrast shifts from proton-density to T2-weighted as the CSF brightens, with the marker tracking the live signal-vs-TE curve" />
</p>

<p align="center"><i>Sweeping echo time (TE) at fixed TR — proton-density → T2-weighted contrast, with the marker moving along the live signal decay curve. Every control updates the image in real time.</i></p>

MRISim models the signal chain from tissue properties and pulse-sequence parameters through k-space acquisition to the reconstructed image, covering the major contrast mechanisms and artifacts seen in clinical MRI.

## Interactive simulator

```bash
python src/app_qt.py
```

<p align="center">
  <img src="docs/screenshot.png" width="900" alt="A spin-echo brain slice with the live T2-decay curve and the acquisition / measurements control panels" />
</p>

The PyQt6 app drives the physics engine in real time:

- **Anatomy** — real BrainWeb brain plus real segmented body regions (Abdomen, Spine, Pelvis, whole Torso) from the TotalSegmentator MRI dataset, each with a synthetic fallback; load any TotalSegmentator NIfTI mask from disk, or index a folder of masks by body region (see [Anatomy and phantoms](#anatomy-and-phantoms))
- **Sequences** — Spin Echo, FSE/TSE (EPG echo train), Gradient Echo, Inversion Recovery, Balanced SSFP (with off-resonance banding), Echo-Planar (EPI), Diffusion (DWI with ADC/FA maps), MR Angiography (TOF / Phase Contrast), fMRI BOLD, and Quantitative (qMRI) parameter mapping
- **qMRI maps** — T1 (variable flip angle), T2 and T2\* (multi-echo), and Synthetic SE contrast rendered from the maps
- **Contrast & field strength** — measured 1.5T / 3T tissue tables, Gadolinium dosing (brain and body, blood-pool weighted), magnetization transfer, B1+ inhomogeneity, flowing-blood signal (spin-echo void / gradient-echo inflow), and three fat-suppression methods (STIR, Dixon in-/opposed-phase, spectral CHESS)
- **Acquisition** — matrix/resolution, FOV (magnify + wraparound when small, surround when large), bandwidth, NEX, partial Fourier, k-space apodisation, parallel imaging (SENSE / GRAPPA / compressed sensing) with g·√R noise, non-Cartesian radial sampling with streaks, and imperfect slice profile + multi-slice cross-talk
- **Artifacts** — motion ghosting (discrete respiratory ghosts), sub-pixel chemical shift, susceptibility dropout, gradient-nonlinearity geometric distortion, zipper
- **Analysis & display** — signal/contrast curves, image histogram, live k-space, pulse-sequence diagrams, tissue-label overlays, multi-slice grids, graphic FOV/slice planning, clinical protocol presets, and SNR / CNR / SAR / scan-time metrics. The viewport carries DICOM-style corner annotations and anatomical orientation labels (radiological convention) on a dark "scanner-console" display.

> `src/app.py` is an earlier matplotlib/Tkinter prototype, retained only for reference and missing most of the above. Use `app_qt.py`.

## Anatomy and phantoms

The engine renders any labelled tissue volume under any sequence. Three sources are available, all sharing the `tissue_db` label vocabulary:

- **Brain (real)** — a BrainWeb digital phantom remapped to gray/white matter, CSF, skull, muscle, blood, marrow and dura, with synthetic skull-base air sinuses for realistic susceptibility/EPI behaviour. **Bundled in the repo** (`data/brainweb_sub04_anat.npy`), so the brain works out-of-the-box; falls back to a synthetic brain only if the file is removed.
- **Body (real)** — Abdomen, Spine, Pelvis and whole-Torso regions built from the **TotalSegmentator MRI dataset** (publicly available on Zenodo). Per-subject organ masks are combined, the subcutaneous-fat / muscle-wall envelope is filled from the real MRI intensity, and a real-MRI texture field modulates the per-label signal so organs show genuine parenchymal detail rather than flat fills. Volumes are resampled to isotropic so axial/coronal/sagittal reformats stay crisp. The processed caches for these four regions are **bundled in the repo and in the downloadable binaries**, so they render with no dataset download.
  - https://zenodo.org/records/14710732
- **Body (synthetic)** — anatomically placed parametric phantoms for Abdomen, Knee, Spine and Pelvis, generated on the fly when no dataset is present. Knee is synthetic-only (the MRI dataset has no suitable knee subject).

<p align="center">
  <img src="docs/screenshot_torso.png" width="900" alt="Real whole-torso anatomy — a coronal spin-echo slice showing heart, lungs, liver, spleen, kidneys, spine and ribs with real-MRI texture" />
</p>

<p align="center"><i>Real whole-torso region (TotalSegmentator MRI, coronal): heart, lungs, liver, spleen, kidneys, spine and ribs rendered with real-MRI texture under a spin-echo sequence.</i></p>

The four default regions above work out of the box (their caches are bundled). To load **other** subjects or rebuild the regions from scratch, make sure `nibabel` is installed (it ships in `requirements.txt`) and place the raw dataset under `data/`:

```
data/TotalsegmentatorMRI_dataset_v200/
  s0246/  s0267/  s0187/  s0250/  ...   # each: mri.nii.gz + segmentations/*.nii.gz
```

The loader auto-detects any `TotalsegmentatorMRI_dataset_v*` release (v1.0, v2.0, …) and caches each region as `.npy` on first load, so subsequent switches are instant. The dataset directory is git-ignored. Default region→subject mapping (chosen for near-isotropic acquisition and full coverage in all three planes) lives in `nifti_region._REGION_TOTALSEG`. You can also:

- **Load File…** — load an arbitrary TotalSegmentator label mask (CT 117-class or MR 50-class, auto-detected) from disk.
- **Browse masks** — index a whole folder of masks, classified by body region, and pick one to render.

## Physics library

All physics lives in tested, importable modules under `src/`; the GUI is a layer over them. Items tagged **(library-only)** are fully usable from Python and covered by tests, but are not yet wired into the GUI.

### Signal physics
- **Spin Echo, Gradient Echo, Inversion Recovery** — closed-form signal equations with T1/T2/PD weighting
- **Fast Spin Echo (FSE/TSE)** — full Extended Phase Graph (EPG) echo-train simulation; handles stimulated echoes and variable flip angles
- **Balanced SSFP (bSSFP/TrueFISP)** — refocused steady state with T2/T1-weighted bright fluid; off-resonance banding nulls at Δf = ±1/2TR
- **Flow** — spin-echo flow void and gradient-echo inflow (time-of-flight) enhancement for moving blood
- **fMRI BOLD** — T2\* modulation via neurovascular coupling, block-design t-statistic maps
- **Diffusion (DWI/DTI)** — mono-exponential and tensor-based signal, ADC/FA maps
- **MR Angiography** — Time-of-Flight inflow enhancement, Phase Contrast velocity encoding

### Advanced contrast
- **Quantitative MRI** — VFA T1 mapping (Fram linearisation), multi-echo T2/T2\* log-linear fitting, IR T1 curve fitting, synthetic contrast generation
- **Dixon fat-water** — two-point (magnitude) and three-point (B0-corrected complex) separation with fat-fraction maps; STIR fat suppression
- **Magnetization Transfer (MT)** — two-pool binary spin-bath model (Henkelman 1993); MTR maps and Z-spectra
- **B1+ inhomogeneity** — Gaussian and sinusoidal transmit field maps; double-angle and AFI B1 mapping sequences

### K-space and acquisition
- **K-space pipeline** — FFT/IFFT, matrix cropping, zero-fill interpolation, Hamming/Hanning/Blackman apodisation, partial Fourier; non-Cartesian radial sampling with streak artifacts
- **EPI** — alternating-readout trajectory, Nyquist (N/2) ghosting, B0 phase-encode distortion, T2\* blurring, phase correction
- **Parallel imaging** — full Cartesian SENSE unfolding (physics-correct g-factor), approximate GRAPPA, variable-density compressed sensing

### Field and hardware effects
- **B0 field maps** *(library-only)* — dipole convolution from susceptibility labels, polynomial shim residuals, Gaussian localised distortions
- **Coil sensitivity** *(library-only)* — head-array simulation, sum-of-squares combination, g-factor maps
- **Rician noise** — correct magnitude-image noise model, SNR estimation, bias correction
- **Partial volume effects** *(library-only)* — sub-voxel tissue mixing

### Geometry and output
- **Oblique slices** — double-oblique prescription, multi-slice slabs, anisotropic voxel spacing
- **Scan geometry** — FOV, matrix, resolution, phase-encode direction, 3-plane localizer overlays
- **Artifacts** — motion ghosting, sub-pixel chemical shift displacement, susceptibility signal loss (internal air), gradient-nonlinearity geometric distortion, zipper
- **Pulse sequence diagrams** — SE, GRE, IR, FSE, Diffusion, balanced SSFP, EPI, TOF and qMRI renderers, each on a physically-ordered local timeline (excitation → echo → readout) with the correct events per sequence
- **Export** — PNG/PDF report export; DICOM export *(library-only)*

## Installation

### Download a ready-to-run app (no Python needed)

Grab the build for your system from the [**latest release**](https://github.com/ea1188/mrisim/releases/latest):

- **Windows** — download `MRISim-windows.exe` and double-click it.
- **macOS** — download `MRISim-macos.zip`, unzip it, drag `MRISim.app` to *Applications*, then allow it on first launch (see [macOS — "can't be opened"](#macos--mrisim-cant-be-opened--apple-could-not-verify) below).
- **Linux** — download `MRISim-linux.tar.gz`, extract it, and run `./MRISim` (needs Qt libraries: `sudo apt-get install libxcb-cursor0 libgl1`).

Each download bundles Python, every dependency, the brain phantom **and the four real body regions** (Abdomen, Spine, Pelvis, whole Torso) — a few hundred MB — so there's nothing else to install and real anatomy works offline. The first launch is slower while font caches build; later launches are quick.

> These builds are **unsigned**, so on first launch your OS may warn that the developer is unidentified (macOS Gatekeeper / Windows SmartScreen). That's expected — see below to allow it.

#### macOS — "MRISim can't be opened" / "Apple could not verify…"

macOS blocks unsigned apps on first launch. To allow it:

1. Double-click `MRISim.app` once. You'll get a warning — click **Done** (or Cancel).
2. Open  **System Settings → Privacy & Security**, scroll down to the **Security** section. You'll see a message like *"MRISim.app was blocked to protect your Mac."* Click **Open Anyway**.
3. Confirm with **Open Anyway** again and authenticate (Touch ID / password) if asked.

On older macOS you can instead **right-click (or Control-click) the app → Open → Open**. After you've allowed it once, it opens normally every time.

If it still won't launch, you can clear the quarantine flag in Terminal:

```bash
xattr -dr com.apple.quarantine /Applications/MRISim.app
```

On **Windows**, if SmartScreen appears, click *More info → Run anyway*.

### Quick version (if you're comfortable with a terminal)

Requires **Python 3.11+** (the code uses `X | Y` union type syntax).

```bash
git clone https://github.com/ea1188/mrisim.git
cd mrisim
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python src/app_qt.py
```

The BrainWeb brain **and the four default body regions** (Abdomen, Spine, Pelvis, Torso) are bundled in the repo, so the app opens on real anatomy with **no dataset download required**. Only loading *other* subjects or regions needs the raw dataset (see [Anatomy and phantoms](#anatomy-and-phantoms)).

### Step-by-step (no terminal experience needed)

Never used a terminal? Follow these in order — you only do steps 1–5 once.

**Step 1 — Install Python (version 3.11 or newer)**

Go to [python.org/downloads](https://www.python.org/downloads/) and download the latest installer for your system, then run it.
- **Windows:** on the first screen of the installer, **tick the box "Add Python to PATH"** before clicking *Install Now*. This matters — without it the commands below won't be found.
- **macOS:** open the downloaded `.pkg` file and click through the installer.

**Step 2 — Open a terminal**

A "terminal" is a window where you type commands.
- **Windows:** click Start, type `PowerShell`, and press Enter.
- **macOS:** press `Cmd` + `Space`, type `Terminal`, and press Enter.
- **Linux:** press `Ctrl` + `Alt` + `T`.

Check Python is installed by typing this and pressing Enter:
```bash
python3 --version
```
You should see something like `Python 3.12.x`. (On Windows, if `python3` isn't found, try `python --version`.)

**Step 3 — Download MRISim**

The easiest way (no extra tools):
1. Open the [latest release page](https://github.com/ea1188/mrisim/releases/latest).
2. Under **Assets**, click **Source code (zip)** to download it.
3. Find the downloaded `.zip` (usually in your *Downloads* folder) and unzip it. You'll get a folder like `mrisim-1.0.0`. Move it somewhere easy, e.g. your *Desktop*.

**Step 4 — Point the terminal at that folder**

In your terminal, type `cd ` (the letters c, d, then a space — don't press Enter yet), then **drag the unzipped folder from your file explorer onto the terminal window**. The folder's location fills in automatically. Now press Enter. For example:
```bash
cd /Users/yourname/Desktop/mrisim-1.0.0
```

**Step 5 — Set up and install (copy-paste one block for your system)**

macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
This creates a private workspace (`.venv`) and downloads everything MRISim needs. It takes a few minutes the first time. (On Windows, if you get a message about scripts being disabled, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, press `Y`, then re-run the activate line.)

**Step 6 — Run the simulator**

```bash
python src/app_qt.py
```
A window opens showing an MRI of a brain. That's it — explore the controls on the side panels.

**Coming back later**

Next time, you only need to open a terminal, `cd` into the folder again (Step 4), re-activate the workspace, and run the app:
```bash
source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
python src/app_qt.py
```

### If something goes wrong

- **`python3: command not found` (or `python`):** Python isn't installed or (on Windows) "Add Python to PATH" wasn't ticked in Step 1. Reinstall Python and try again.
- **`No such file or directory` after `cd`:** the terminal isn't in the project folder. Redo Step 4 (the `cd` + drag trick).
- **`No module named ...` when running the app:** the install step didn't finish or the workspace isn't active. Make sure you ran the Step 5 block and see `(.venv)` at the start of your terminal line, then re-run `pip install -r requirements.txt`.
- **Linux only — `could not load the Qt platform plugin "xcb"`:** install the system graphics libraries the window needs:
  ```bash
  sudo apt-get install libxcb-cursor0 libgl1
  ```
  On a headless server (no screen), run under a virtual display: `xvfb-run python src/app_qt.py`.
- **Optional extras:** `nibabel` (already installed in Step 5) loads real body anatomy; the `brainweb` package is only needed to regenerate the brain or use a different BrainWeb subject.

> **Technical note:** the source modules import each other by bare name, so they expect `src/` on the import path. Running `python src/app_qt.py` handles this automatically (Python puts the script's directory first on `sys.path`), as does the test suite via `tests/conftest.py`. If you import the modules yourself, run from `src/` or set `PYTHONPATH=src`.

## Running tests

From the repository root (`tests/conftest.py` puts `src/` on the path and forces a non-interactive matplotlib backend):

```bash
pytest                  # or: python -m pytest
```

1,790+ tests, all passing. Coverage is 97%+ across all non-GUI modules. CI also runs `ruff` (lint) and strict `mypy` (type-checking) on every push. (The tests covering the legacy `src/app.py` prototype need its `gradio` dependency, which `requirements.txt` installs.)

## Project layout

```
src/                  # all source modules (plain imports by bare name)
  app_qt.py           # PyQt6 interactive GUI
  rendering.py        # Qt-free signal-rendering helpers (tested)
  signal_engine.py    # SE / GRE / IR signal equations, SNR, scan time
  simulate.py         # thin orchestration layer
  phantom.py          # 2-D brain phantom (labels 0–4)
  phantom3d.py        # 3-D synthetic brain (labels 0–5)
  body_phantoms.py    # body region registry + synthetic abdomen/knee/spine/pelvis
  nifti_region.py     # load real TotalSegmentator MRI anatomy (masks + texture)
  region_index.py     # classify/index a folder of NIfTI masks by body region
  brainweb_loader.py  # load + remap the real BrainWeb brain phantom
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
  artifacts.py        # motion, chemical shift, susceptibility, distortion, zipper
  flow.py             # flowing-blood signal (SE void / GRE inflow)
  pv.py               # partial volume effects
  angiography.py      # TOF and phase-contrast MRA
  dicom_export.py     # DICOM export
  version.py          # single-source __version__
  ...
tests/                # pytest suite (one file per module)
data/                 # phantom/atlas cache + optional TotalSegMRI dataset (git-ignored)
```

See [`CHANGELOG.md`](CHANGELOG.md) for the release history and versioning policy.

## Physics references

- Henkelman et al. (1993) *MRM* 29:759 — two-pool MT model  
- Fram et al. (1987) *MRM* 4:306 — VFA T1 linearisation  
- Glover (1991) *J Magn Reson Imaging* 1:521 — three-point Dixon  
- Pruessmann et al. (1999) *MRM* 42:952 — SENSE reconstruction  
- Weigel (2015) *J Magn Reson Imaging* 41:266 — EPG formalism
