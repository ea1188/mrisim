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

### Added
- **Visible localizer handles + cursor feedback (both editions).** The browser
  localizer now changes the **cursor on hover** to show what each region does (move
  the box / sat band, resize a corner, grab to angle), and both editions draw
  **corner handles** on the FOV box so it reads as resizable. Makes the on-image
  controls discoverable at a glance.
- **Browser localizer angling: on-image readout + angle snapping.** The browser
  localizer now draws a pivot and the **angle this panel controls** (`±N°`) next to
  each tilted oblique band, so the obliquity reads on the image itself. Dragging a
  band to angle the plane now **magnets onto common angles** (0 / ±15 / ±30 / ±45) —
  parity with the desktop gizmo + snap.
- **Drag the saturation band on the browser localizer.** The browser previously
  only had sliders for the sat band; now it's drawn on the acquired-plane panel as a
  tinted strip you can **drag to move** and **grab an end handle to angle** — parity
  with the desktop. `web_adapter.render_scout` draws the band and ships its panel-
  local geometry to the front-end; `app.js` hit-tests and drags it (the angle math
  undoes the panel's display aspect so it tracks the cursor).
- **Clearer oblique-angle gizmo + angle snapping (desktop).** The FOV-planning
  localizer now draws a rotation **pivot**, an **arc** sweeping to the current oblique
  angle, and a live **tilt° / rot°** readout, so the centre and amount of angulation
  are obvious. Dragging an angle handle now **magnets onto common angles** (0 / ±15 /
  ±30 / ±45) so it's easy to land on a clean value.
- **Place the saturation band on the localizer (desktop) + angled bands (both
  editions).** The sat band is now drawn on the FOV-planning localizer as a tinted
  strip you can **drag to move** and **grab an end handle to angle** — with matching
  hover cursors. The engine's `apply_sat_band` gained an `angle`, so a tilted band
  nulls a diagonal strip (the desktop also exposes a **Sat band angle** slider, and
  the browser gets the angle control). Angle 0 stays the fast axis-aligned path.

## [1.26.0] — 2026-06-14

### Added
- **Phase-encode direction swap + prescription presets in FOV planning.** A **Swap
  phase-encode direction** toggle (shared engine, both editions) flips which in-plane
  axis is the phase-encode direction, so the FOV wraparound folds the *other* way —
  the way swapping PE on a scanner moves the wrap (and motion ghosts). And on the
  desktop a **Prescription** dropdown applies common geometry setups in one click
  (whole-brain axial, hi-res axial, sagittal survey, coronal thin) — plane + slice
  group + in-plane FOV.
- **Saturation bands in FOV planning — both editions.** A new **Saturation band**
  toggle (with position and width controls) nulls a strip of the acquired image —
  saturated spins give no signal — the way a real sat band suppresses signal from a
  region (inflowing vessels, motion). Shared engine (`scan_geometry.apply_sat_band`)
  so the desktop and browser both get it; the desktop also tints the band on the
  prescribed montage so it's clearly deliberate.
- **Discoverable localizer handles (desktop).** It wasn't obvious the FOV-planning
  localizer was interactive. Now the cursor changes as you hover to show what each
  region does — **✛ move** over the box interior, **⇔ / ⇕ resize** over the FOV /
  coverage edges, and a **✋ grab-to-angle** pointer over the through-edges for
  oblique — with a clearer one-line legend under the controls. The drags themselves
  are unchanged; they're just findable now.
- **Prescription readout + warnings in FOV planning (desktop).** The planning
  controls now show a live summary of the prescription — number of slices,
  thickness, gap, through-plane coverage, and the in-plane FOV in both % and mm —
  with amber warnings when the slab runs past the volume edge, leaves through-plane
  gaps (may miss small lesions), or prescribes a phase FOV smaller than the anatomy
  (wraparound). Makes the consequences of a prescription legible at a glance.
- **FOV phase wraparound (aliasing) in planning — both editions.** Reducing the
  in-plane FOV used to simply *crop* the image; now a phase-FOV smaller than the
  anatomy **folds over** to the opposite side — the real wraparound artifact, and
  the single most important FOV-planning lesson. The readout direction is cropped
  cleanly (it's oversampled and doesn't alias), so only the phase axis wraps. A new
  **Phase oversample (no wrap)** toggle suppresses it (clean crop). Implemented in
  the shared engine (`scan_geometry.fov_crop(..., wrap=True)`), so the desktop and
  browser both get it.

## [1.25.2] — 2026-06-14

### Fixed
- **Duplicate `flow_velocity` control.** The desktop declared `flow_velocity` twice
  — a phase-contrast blood velocity (cm/s) that was silently shadowed by the
  flow-artifact velocity (0–100%) — leaving the PC velocity dead. The PC one is now
  a distinct `pc_flow_velocity` with its own **Flow velocity (cm/s)** slider in the
  phase-contrast controls, wired through to the engine. A nice side effect: PC
  velocity aliasing can now be shown by raising the flow above the VENC, not only
  by lowering the VENC.

## [1.25.1] — 2026-06-14

### Fixed
- **Desktop teaching-map panels went stale in some modes.** The contrast / B0 /
  g-factor panels are drawn at the end of `recalculate`, but the FOV-planning,
  reconstruction (MPR/MIP) and multi-slice paths return early before reaching it —
  so a panel toggled on would linger with stale content (or not appear) in those
  modes. The maps now redraw in every render path.
- **Phase-contrast controls didn't follow a lesson-set MRA type.** The VENC / PC
  Display controls now track `angio_type` via a write-trace, so a guided lesson or
  share link that selects Phase Contrast reveals them too (not just the dropdown).

## [1.25.0] — 2026-06-14

### Added
- **Phase-contrast MR angiography (new physics, both editions).** The MRA sequence
  previously only ever rendered a Time-of-Flight MIP — `angio_type` was ignored, so
  selecting "Phase Contrast" still showed TOF on both the desktop and the browser.
  The shared engine now has a real PC path (`angiography.pc_intensity_volume` →
  `Simulator._pc_volume`): velocity is encoded as phase (φ = π·v/venc) and projected
  as a velocity-weighted angiogram, so a **VENC** below the true flow visibly aliases
  fast vessels (the core PC teaching point). The desktop gains an **MRA Type**
  selector (TOF / Phase Contrast) with **VENC** and **PC Display** (Speed / Magnitude)
  controls; the browser benefits automatically (sensible defaults). This unlocks the
  last two guided lessons on the desktop — "TOF vs phase-contrast angiography" and
  "Choosing the protocol (capstone)" — so **all 36 lessons** now run on the desktop.
- **Teaching map panels on the desktop (parity with the browser).** Three optional
  side panels in the Display section that visualise *why* the image looks the way
  it does: a **contrast map** (the |S_a − S_b| landscape across the whole TR×TE
  plane for a representative tissue pair, with the current protocol marked), a
  **B0 field map** (the off-resonance field in Hz that warps EPI and shifts fat),
  and a **g-factor map** (local SENSE noise amplification, shown once the
  acceleration R > 1). The data reuses the shared engine (`_curve_signal`,
  `Simulator._b0_field_slice`, `coil.g_factor_map`). This unlocks three more
  guided lessons on the desktop ("Where contrast comes from", "Parallel imaging &
  the g-factor", "B0 inhomogeneity & EPI distortion").
- **Guided feature tour on the desktop (parity with the browser).** The desktop app
  had no onboarding; it now has a **❔ Tour** button (and a first-run offer) that
  walks through the main controls — sequence, timing, the image, presets, A/B
  compare, 3D & reconstruction, measure, find-a-control — highlighting each with a
  rubber-band + tooltip (Back / Next / Skip), expanding collapsed sections and
  scrolling them into view as it goes.
- **Demo brain pathologies on the desktop (parity with the browser).** A new
  **Pathology (demo)** picker in 3D Navigation paints a teaching lesion into brain
  white matter — MS plaques, a focal lesion, an acute infarct, a microhaemorrhage,
  an enhancing tumour, or an abscess (enhancing rim + pus core) — so contrast
  behaviour (e.g. FLAIR/T2 conspicuity, rim enhancement) can be demonstrated. The
  painting logic is now shared with the browser via `rendering.paint_brain_pathology`
  (single source of truth; labels 23–28 render through the field-synced tissue
  table). Brain-only; cached per kind; a no-op for body regions.
- **Guided lessons on the desktop (parity with the browser).** A new **📚 Lessons**
  button opens a step-by-step lesson runner: a docked strip under the viewport
  shows each step's explanation and drives the actual controls for you (Back /
  Next / Exit), including A/B comparisons and demo pathologies. The lesson content
  is now authored once in `data/lessons.json` — the **single source** the browser
  fetches at runtime and the desktop reads directly — so the two stay in sync.
  Lessons that rely on a panel the desktop lacks are filtered out automatically;
  with the teaching-map panels and phase-contrast angiography above, **all 36
  lessons** run on the desktop in this release.

### Changed
- Refactored the browser's `_pathology_volume` to delegate to the shared
  `rendering.paint_brain_pathology`, removing the duplicated painting code.
- The browser now fetches its guided-lesson data from `lessons.json` (copied into
  `web/` by `build_web.py`) instead of inlining it in `app.js`, so the desktop and
  browser share one lesson source. The offline service-worker precache (bumped to
  `mrisim-v2`) includes it.

## [1.24.0] — 2026-06-13

Robustness and content. The browser no longer freezes if the Pyodide engine
crashes (it surfaces an error and tells you to reload), and there's new teaching
content: a **multiple-sclerosis** demo pathology and two more lessons (slice
thickness / partial volume, and receiver bandwidth). Plus review polish and wider
rendering-invariant test coverage under the hood.

### Added
- **Multiple-sclerosis demo pathology (browser).** A new Pathology option that
  scatters several periventricular white-matter plaques (FLAIR-bright), for the
  classic "count the lesions" MS reading — it reuses the existing lesion tissue, so
  no engine change.
- **Two more guided lessons (browser).** **"Slice thickness & partial volume"**
  (thick = bright but blurry vs thin = sharp but noisy) and **"Bandwidth — the
  hidden three-way trade"** (SNR vs chemical-shift vs readout speed) — filling two
  fundamental gaps in the lesson set.

### Fixed
- **Engine-crash resilience (browser).** If the Pyodide worker ever crashes (e.g.
  out of memory) it fires an `error` event rather than returning a result; without
  a handler, in-flight requests hung forever and the UI froze silently. Now a
  `worker.onerror` handler fails the pending calls, clears the busy state, and shows
  "Engine error — please reload," and later calls reject immediately instead of
  hanging.
- **Review polish (browser).** The welcome no longer hard-codes "three" Start-here
  lessons (there are four); the **receive coil** is now part of shareable links
  (parity with the curve state); and the feature tour skips a step whose target is
  hidden (e.g. the curve panel when the curve is off) instead of showing an empty
  spotlight.

## [1.23.0] — 2026-06-13

Onboarding: new visitors get a **guided feature tour** — a spotlight walkthrough
of the real controls, offered on the welcome screen and re-launchable from the
**?** help hub — plus **five more guided lessons** (gadolinium, receive coils,
balanced SSFP, SWI and fMRI).

### Added
- **Guided feature tour (browser).** A first-run welcome now offers a **"Take the
  feature tour"** — a spotlight walkthrough that points at the real controls
  (sequence, timing, the image, the curve, presets, compare, 3D reconstruction,
  measure, find-a-control, lessons) with Back / Next / Skip. Re-launchable anytime
  from the **?** button, which is now the help/welcome/tour hub.
- **Five more guided lessons (browser).** New walkthroughs on **gadolinium
  contrast** (why post-contrast is T1), **receive coils** (surface vs array
  shading, tying in the coil feature), **balanced SSFP** (bright fluid + banding),
  **SWI** (veins, iron, blooming microbleeds), and **fMRI BOLD** (activation /
  t-statistic maps). The lesson engine now also applies the receive-coil setting.

## [1.22.0] — 2026-06-13

Small polish: a desktop **hide-curve** toggle (giving the image the full width when
the curve, k-space and A/B comparison are all off), and **shareable links that
preserve the signal-curve type and visibility** in the browser.

### Added
- **Hide the signal curve on the desktop.** A "Show signal curve" toggle (Display
  section). With it off — and no k-space panel or A/B comparison — the second panel
  is dropped and the image spans the full width; toggling it (or k-space / compare)
  back restores the side-by-side layout.
- **Curve state in share-links (browser).** A shareable link now preserves the
  signal-curve type (TE decay / TR recovery / … / Flip angle) and whether the curve
  is shown, so a link reproduces the exact view.

## [1.21.0] — 2026-06-13

Desktop catches up to the browser. The desktop app gains the three features the
browser got in v1.20.0: **interactive ruler/ROI measurement** (on the main image
and the 2×2 reconstruction), **receive-coil shading**, and **perceptual,
colorblind-safe colormaps + calibrated colorbars** on the quantitative maps. The
colormap, coil-envelope and measurement code is now shared between both apps.

### Added
- **Interactive measure tools on the desktop (ruler + ROI).** The desktop app gains
  on-image measurement to match the browser — pick **Ruler** or **ROI** (Display
  section) and drag on the image to read a distance in mm or an ROI's mean / SD /
  SNR / area. It works on the main image **and on each 2×2 reconstruction panel**.
  The ruler/ROI statistics are now a shared `rendering.measure_stats` used by both
  apps.

### Changed
- **Quantitative maps use perceptual, colorblind-safe colormaps + a colorbar on the
  desktop too (parity with the browser).** T1 / T2 / T2\* (qMRI) and ADC / FA
  (diffusion) maps render with a perceptually-uniform colormap (viridis / magma /
  cividis) and a calibrated colorbar (the user's colormap pick still applies to
  weighted images, and overrides the default on maps). The map/colormap mapping is
  now a shared `rendering.quantitative_map_spec` used by both apps.

### Added
- **Receive-coil shading on the desktop (parity with the browser).** A "Receive
  coil" picker (Spatial / Acquisition) — ideal, 8-channel head array, 2-channel
  quadrature or surface coil — shades the image by the coil's spatial sensitivity.
  The envelope is now a shared `coil.receive_coil_envelope` used by both apps.

## [1.20.0] — 2026-06-13

More ways to read the physics, and a clearer, more honest picture. New in the
browser: an **Ernst-angle flip-angle curve**, **measure (ruler/ROI) on the 3D
reconstruction** reformats, **receive-coil shading** (surface vs array), and
**perceptually-uniform, colorblind-safe colormaps with calibrated colorbars** on
the quantitative T1/T2/T2\*/ADC/FA maps. The README also gains a proper Browser-
edition section covering the guided lessons, curriculum and offline support.

### Added
- **Measure on the reconstruction (browser).** The ruler and ROI tools now work on
  the 2×2 MPR reformats (and the single MIP/oblique panels), not just the main
  image — drag on any panel to read a distance in mm or an ROI's mean / SD / SNR /
  area, computed on that reformat's real pixels. Selecting a measure tool switches
  the panels from click-to-navigate to measuring.
- **Receive-coil shading (browser).** A "Receive coil" picker — ideal (uniform),
  8-channel head array, 2-channel quadrature, or a single surface coil — modulates
  the image by the coil's spatial sensitivity (from the tested `coil.py` models): a
  surface coil shows the characteristic strong one-sided falloff, arrays cover the
  whole FOV but still vary, illustrating why scanners apply intensity correction.

### Changed
- **Quantitative maps use perceptual, colorblind-safe colormaps + a colorbar
  (browser).** T1 / T2 / T2\* (qMRI) and ADC / FA (diffusion) maps now render with a
  perceptually-uniform, colour-vision-deficiency-safe colormap (viridis / magma /
  cividis) and a calibrated colorbar in real units (ms, ×10⁻³ mm²/s), instead of an
  uncalibrated grayscale. Grayscale/rainbow maps are a well-documented source of
  misreading; weighted images stay grayscale. The colorbar is overlaid so the image
  still fills its frame (probe / measure / window-level mapping is unchanged).

### Added
- **Ernst-angle (flip-angle) signal curve (browser and desktop).** A new "Flip
  angle" signal-curve mode sweeps the flip angle and plots signal vs flip for
  white matter / gray matter / CSF, marking each tissue's **Ernst angle**
  (cos α = e^−TR/T1) and your current flip. Gradient-echo shows the classic peak;
  flip-independent sequences (spin-echo, IR) render a flat line — itself the point.

## [1.19.0] — 2026-06-13

A round of viewing improvements and durability work. In the browser you can now
hide or switch the signal curve (T2 decay, T1 recovery, inversion or a histogram),
and 3D reconstruction opens as a PACS-style 2×2 quad — three reformats plus a 3-D
MIP overview — on both the browser and the desktop. Under the hood: shareable
links are versioned, the browser works offline after first load (a conservative,
network-first service worker), and CI gained ESLint and rendering-invariant
regression tests.

### Added
- **Offline support + CDN resilience (browser).** A conservative service worker
  caches the app so it works **offline after the first load** and survives CDN
  hiccups. It is deliberately *network-first* for the app shell — online visitors
  always get the latest code, the cache is only an offline fallback — and
  *cache-first* only for immutable, versioned assets (the pinned Pyodide runtime +
  wheels, and the build-id-busted engine/anatomy), so it can never serve stale app
  code. Includes a kill-switch path and an offline smoke test.
- **Versioned share-links (browser).** Shareable links now carry a schema version
  (`v=`) with a `migrateState()` hook, so a link made with an older build is
  brought up to date rather than silently misapplied, and a link from a newer
  build still applies what it can instead of breaking.
- **Signal-curve controls (browser).** A toggle to hide/show the signal-curve
  panel, and a "Curve type" picker to switch what it plots — **TE decay** (T2),
  **TR recovery** (T1), **TI sweep** (inversion) or a **signal histogram**. (The
  engine already supported these modes; the browser just hadn't exposed them.)

### Changed
- **3D reconstruction opens as a 2×2 grid (browser and desktop).** MPR now shows
  the three reformats (axial / coronal / sagittal) **plus a 3-D MIP overview** of
  the whole slab in the 4th quadrant — the PACS-style quad layout — instead of a
  three-wide strip, so each panel is larger and the volume has a 3-D reference. The
  reconstruction PNG export (browser) now includes the overview panel too.

### Internal
- **Rendering-invariant regression tests.** New `tests/test_visual_regression.py`
  decodes the engine's PNG output and asserts the visual failure modes that
  array-level tests miss and have regressed before — blank/collapsed panels and
  **stretched (wrong aspect-ratio) reformats** (each MPR panel's PNG aspect must
  match its data aspect). Uses invariants rather than pixel baselines (the loose
  matplotlib pin would make pixel baselines flaky across CI matplotlib bumps).
- **ESLint for the browser build.** Added an ESLint flat config and a fast,
  path-filtered CI job that statically checks `web/app.js`, `web/worker.js` and
  `web/smoke.mjs` on every PR — catching undefined variables, typos, duplicate
  keys and unreachable code that the headless-browser smoke test can't see.

## [1.18.0] — 2026-06-12

The control panel becomes easier to navigate and to set precisely, on both the
browser and the desktop: type or arrow-key an exact value into any slider, jump
straight to a parameter with a "Find a control" search, and work in a shorter,
collapsible panel with the visualization toggles grouped together.

### Added
- **Control search (browser and desktop).** A "Find a control…" box at the top of
  the panel filters the controls as you type (e.g. "bandwidth", "flip"), showing
  only the matching sections and opening them — so you can jump to a parameter
  without scrolling or knowing which group it's in.
- **Editable numeric values (browser and desktop).** Every parameter slider now has
  a paired editable field: type an exact value (TR = 2200, TE = 80…) or arrow-key
  it, and the slider and image follow. Previously values were drag-only and
  read-only. (Desktop already had collapsible control sections and a grouped
  Display section, so this completes the parity with the browser's panel work.)

### Changed
- **Collapsible control groups (browser).** The control panel's sections now
  collapse and expand from their headers, with the core groups (Protocol, Anatomy &
  Sequence, Timing, Contrast) open and the advanced ones (Acquisition, Artifacts,
  Visualizations, Measure, 3D, Parallel imaging) collapsed by default — a much
  shorter scroll. Each section remembers its open/closed state per device.
- **Visualizations grouped (browser).** The six overlay/side-panel toggles
  (contrast map, k-space, pulse-sequence diagram, B0 map, g-factor map, show-math)
  moved out of the overloaded "Anatomy & Sequence" group into their own
  **Visualizations** section.

## [1.17.0] — 2026-06-12

The 3D reconstruction view becomes a proper mini-workstation: one panel for
acquisition + reconstruction, a slab that covers the whole anatomy from the first
click, MinIP/AIP projections, click-to-navigate MPR, a movable slab with PNG export,
a rotating-MIP cine, true-proportion panels with calibrated scale bars — on both the
browser and desktop — plus reconstruction/protocol lessons and a curriculum capstone.

### Changed
- **3D acquisition and reconstruction are now one panel (browser).** The separate
  "3D acquisition" and "3D reconstruction" groups are merged into a single **3D
  acquisition & reconstruction** section, so you set up the slab and reformat it in
  one place.
- **A 3D slab now covers the whole anatomy from the first click (browser and
  desktop).** Enabling the slab spans the full slice axis by default (was a thin
  32-partition slab), so the reconstruction's coronal/sagittal reformats are full
  immediately instead of thin strips. The "Slab depth" slider still thins it down, and
  its range tracks the volume. The reconstruction lessons now use the full slab too
  (so they show full reformats), and the desktop projection views gain the same
  calibrated scale bar as the browser.

## [1.16.1] — 2026-06-12

Reconstruction-view polish: the MPR/projection panels no longer stretch, and the
projection views gain a calibrated scale bar.

### Fixed
- **Reconstruction panels no longer stretch.** The MPR reformats (and the desktop
  recon panels) were stretched to fill their box — a thin slab's coronal/sagittal
  reformats came out badly distorted. Panels now keep their **true proportions** (a
  thin slab reformats to a thin strip; use more partitions for taller reformats),
  while click-to-navigate still maps correctly.

### Added
- **Calibrated scale bar on the projection reconstructions (browser).** The MIP /
  MinIP / AIP / oblique / rotating recon views now carry a tidy mm scale bar (sized
  from the region's voxel size), so reformats have a spatial reference. (The
  aspect-stretched MPR panels keep the crosshair instead.)

## [1.16.0] — 2026-06-12

A reconstruction-workstation upgrade: MinIP/AIP projections, click-to-navigate MPR
(both apps), a movable slab with PNG export, and a rotating-MIP cine — plus three new
lessons and a curriculum capstone.

### Added
- **Three new lessons + a curriculum capstone module (browser)** (26 → 29 lessons):
  "MIP, MinIP & AIP — projecting a slab", "TOF vs phase-contrast angiography", and a
  "Choosing the protocol" capstone (clinical question → sequence, plane, options). The
  curriculum gains a 9th module, **Putting it together**, ending on the capstone.
- **Rotating-MIP cine (browser).** In the reconstruction view's rotating-MIP mode, a
  **Spin cine** button pre-renders a full 360° stack of frames and animates them
  client-side for a smooth spinning angiogram — like rotating a MIP on a workstation.
  Any manual interaction stops it.
- **Movable slab position + reconstruction PNG export.** The thick-slab projection
  gains a **Slab position** slider (slide the slab through the volume, not just
  resize it), on browser and desktop. The browser adds a **Download recon PNG** button
  (the single projection, or the three MPR reformats).
- **Click-to-navigate the MPR (browser and desktop).** In the reconstruction view's
  MPR mode, click any of the three reformat panels to move the crosshair there — the
  other two planes update to match, like a real workstation (the crosshair sliders
  still work too). Browser panels render edge-to-edge so the click maps precisely;
  the desktop maps the matplotlib data coordinate of the clicked panel.
- **MinIP and AIP projections in the reconstruction view.** The thick-slab MIP now
  offers a **Projection** picker: **MIP** (brightest — vessels, fluid), **MinIP**
  (darkest — vessels on SWI, air) and **AIP** (average — the CT-style slab mean), on
  both browser and desktop. The engine reducer is shared and tested
  (`reconstruction.thick_slab_projection`), and the endpoint also accepts a movable
  slab position (`mip_center_frac`).

## [1.15.0] — 2026-06-12

A guided beginner curriculum threads the lessons into an ordered learning path, and
window/level now works (on both panels) in A/B compare.

### Added
- **Guided curriculum for beginners (browser).** A new "🎓 Curriculum" launcher
  threads the 26 lessons into an ordered, eight-module path — from *what an MRI
  image is* through contrast, pathology, image quality, k-space, 3D/reconstruction
  to flow/function/artifacts. It tracks progress on the device (saved locally), shows
  a progress bar and per-module ticks, and **Continue** resumes the first unfinished
  lesson; finishing one lesson advances straight to the next in the path.
- **Window/level works in A/B compare — and re-windows both panels.** Previously the
  window/level drag was disabled while comparing two protocols. Now dragging on
  either image adjusts the shared window/level and re-windows **both** A and B
  together, so the contrast comparison stays fair (browser and desktop).

## [1.14.0] — 2026-06-11

The 3D reconstruction view comes to the desktop, so the downloadable app gains the
same MPR / MIP / oblique reformats the browser shipped in v1.13.0.

### Added
- **3D reconstruction view on the desktop.** The PyQt app gains the same
  reconstruction the browser got: a "Reconstruction view" toggle that turns the
  acquired 3-D slab into **MPR** (three orthogonal reformats with a crosshair),
  **thick-slab MIP** (plane + thickness), **rotating MIP** (azimuth/elevation) and
  **oblique MPR** (tilt/rotate) — driven by the shared, tested `reconstruction.py`.

## [1.13.0] — 2026-06-11

A reconstruction workstation in the browser: turn an acquired 3D slab into MPR,
thick-slab MIP, rotating MIP and oblique reformats — all from the one acquisition.

### Added
- **3D reconstruction view (browser).** Once a 3D slab is acquired, a Reconstruction
  panel turns it into **MPR** (three orthogonal reformats with a linked crosshair),
  **thick-slab MIP** (adjustable thickness + plane), **rotating MIP** (any angle) and
  **oblique MPR** (arbitrary tilt/rotate) — all from the one acquisition. Backed by a
  new tested `reconstruction.py` engine module + a `reconstruct()` endpoint. A new
  "Reconstructing the 3D slab" lesson walks through it.

## [1.12.0] — 2026-06-10

Browser parity with the desktop's teaching tools: advanced-sequence displays,
k-space and pulse-sequence-diagram panels, parallel-imaging controls with g-factor
and B0 field maps, and six new guided lessons — plus honest coverage numbers and a
CI coverage floor.

### Changed
- **Honest coverage numbers + a CI coverage floor.** The README claimed "97%+
  non-GUI / ~94% GUI"; the measured figures are ~94% non-GUI, ~74% GUI, ~87%
  overall — corrected in the README. CI now enforces `--cov-fail-under=85` so new
  untested code fails the build.

### Added
- **Parallel imaging + physics-map views in the browser.** New parallel-imaging
  controls (acceleration **R** + method), a **partial-volume** slider (desktop
  parity), and two map panels that surface previously library-only physics: a
  **g-factor map** (SENSE noise amplification, via `coil.g_factor_map`) and a **B0
  off-resonance field map** (the susceptibility inhomogeneity that warps EPI). Two
  new lessons use them: "Parallel imaging & the g-factor" and "B0 inhomogeneity &
  EPI distortion".
- **k-space and pulse-sequence-diagram panels in the browser.** Two new toggles
  show the raw **k-space** (log-magnitude of the acquired data the image is the
  Fourier transform of) and the **pulse-sequence diagram** for the current sequence
  (RF/gradient/echo timing) — both reusing the desktop's renderers. A new "Reading
  k-space" lesson ties matrix size to k-space coverage and the image's sharpness.
- **Advanced-sequence displays in the browser.** The web build now exposes the
  per-sequence display modes the desktop has: diffusion **DWI / ADC / FA**,
  angiography **TOF / Phase-Contrast**, the **qMRI map** picker (T1 / T2 / T2* /
  Synthetic SE) and the **fMRI** display — plus **7 T** as a field strength. Two new
  lessons use them: "DWI vs ADC — is the restriction real?" and "qMRI — measuring
  tissue, not a picture" (23 lessons total).

## [1.11.0] — 2026-06-10

Teaching depth: the 3D slab now explains what it buys, presets genuinely drive 3D
acquisition, and five new guided lessons (plus six new clinical presets) round out
the sequence-physics and advanced-contrast curriculum.

### Added
- **5 new guided lessons (browser)** (16 → 21): the Ernst angle (flip for maximum
  signal), resolution vs SNR (the matrix trade-off), fat suppression (STIR vs
  spectral CHESS), in- vs opposed-phase (Dixon, the India-ink sign), and bright-blood
  angiography (TOF). The existing 3D-slab lesson gains steps on the √Nz SNR gain and
  kz partial Fourier.
- **6 new clinical presets** (53 → 59): Brain 3D FLAIR, Brain 3D T2 (SPACE),
  Abdomen 3D GRE (VIBE), DTI FA Map, Knee T2 Map (qMRI) and Cardiac LGE.
- **3D slab readout + slab-profile control (browser).** The 3D-acquisition panel
  now shows what the partition count buys — isotropic partition thickness, total
  slab coverage and the √(Nz·NEX) SNR gain over a single 2D slice — and exposes the
  slab-profile sharpness so you can see the slab-edge signal falloff. The engine
  reports these as metrics (`is_3d`, `n_partitions`, `partition_mm`, `slab_mm`,
  `snr_3d_gain`); the desktop voxel-size readout now uses the true partition
  thickness in 3D.

### Changed
- **Presets now actually drive 3D acquisition.** Presets could carry a 3D flag but
  neither app applied it, so the "3D" presets were 3D in name only. MPRAGE, CISS and
  Knee GRE T2* are now genuinely acquired as 3D slabs (reformatting to any plane),
  and the preset-apply path honours `acq3d` / `n_partitions` in both the desktop and
  browser builds.

## [1.10.1] — 2026-06-10

A correctness-and-polish patch from a pre-release review: the FOV-planning
localizer no longer clips, sagittal regions open on their true midline, rendering
is reproducible, and the legacy Gradio prototype and a divergent fMRI copy are gone.

### Removed
- **Legacy Gradio prototype.** Removed the unused root `app.py` (Gradio web
  front-end) and its `lessons.py` / `annotations.py` helpers and three test files,
  and dropped the `gradio` dependency from `requirements.txt` — a smaller install
  and less 0%-covered surface area. The maintained GUIs (`app_qt.py` desktop, the
  Pyodide browser build) are unaffected.
- **Divergent fMRI copy.** Removed `fmri.simulate_fmri_image` / `simulate_bold_signal`
  (a duplicate of `simulate_fmri_fast` that used a different T2\* table and law and
  wasn't on any render path) and their tests; the engine's fMRI uses
  `phantom3d_extended.simulate_fmri_3d_slice`.

### Fixed
- **FOV planning showed only the top half of the 3-plane localizer.** The scout
  image sat in a fixed-height box and overflowed it, so the box clipped the
  localizer to its top. The box now sizes to the localizer's natural height
  (capped), so the whole thing is visible — and click/drag prescription is
  unchanged.
- **Spine and Knee open on their plane's midline, not a body-edge slice.** Loading
  a region whose canonical plane is sagittal jumped the engine to the middle of the
  *axial* axis instead — so the Spine opened on slice 111 of a 128-deep left-right
  axis, a near-lateral cut, and the slice slider got the wrong range. The engine's
  orientation is now synced before the mid-slice is chosen, so these regions open
  centred on their true midline. (The 3-plane localizer geometry itself was already
  correct.)
- **Rendering is now deterministic.** The Rician noise was the one stochastic step
  left unseeded, so every re-render reshuffled the noise — the image shimmered when
  you toggled an overlay or scrolled back to a slice, and an A/B comparison differed
  partly by chance. It now seeds off the slice, orientation and noise level: identical
  settings give an identical image, while any noise-affecting change still draws a
  fresh realization. (This also surfaced that the susceptibility artifact is a no-op
  on the brain — no internal air cavities — and is refocused by spin echo; its test
  now exercises it on the abdomen with a gradient echo, where the dropout is real.)
- **FOV planning: double-oblique now works.** Dragging the slice band only ever
  changed one angle (tilt), because both cross panels were tagged the same way and
  the front-end mapped them both to tilt. Each cross panel now carries its own
  oblique degree of freedom, so dragging the band in one cross view angles the
  plane one way (tilt) and the other view angles it the other way (rot) — you can
  prescribe a genuinely double-angled slice. (The engine already supported it.)
- **Dialogs always fit the screen.** With the full set of lessons (and on short
  viewports) the lesson picker and the welcome intro could run off the page and
  push their buttons out of reach. Both are now **height-capped cards whose body
  scrolls** while the title, footer and a new **corner ✕** stay pinned — so you can
  always close them (the ✕ also lets you exit the lesson picker without picking
  one). The floating active-lesson panel is likewise capped so a long step scrolls
  rather than pushing its Back/Next buttons off-screen.
- **Rician `rician_mean` / `rician_variance` are now exact at all SNR.** `rician_mean`
  returned only the high-SNR √(ν²+σ²) approximation, which made `rician_variance`
  collapse to a constant σ² for every ν. Both now use the exact Laguerre closed
  form (overflow-safe via scaled Bessel functions) — verified against Monte-Carlo
  (e.g. ν=0 ⇒ mean 1.2533σ, var 0.4292σ²), with low-SNR regression tests added.
- **PC-MRA velocity-aliasing wrap** was off by π; phases above venc now wrap
  correctly into (−π, π] (`(φ+π) mod 2π − π`).
- Removed a dead statement in the fMRI t-map (made the rest/active split explicit)
  and corrected a gyromagnetic-ratio typo (42.576→42.577 MHz/T) so it matches the
  rest of the engine.

### Added
- **Vertical slice rail beside the image.** A slider sits next to the image you can
  drag up/down to scroll through slices — handy on a tablet or phone where there's
  no scroll wheel. It stays in sync with the wheel, arrow keys, the controls-panel
  slider and the scout, and announces the slice number to screen readers. The rail
  spans the full image height (sized in JS), so a small drag moves a few slices
  rather than the whole stack.

## [1.10.0] — 2026-06-09

Clinical depth and accessibility: a ring-enhancing abscess, instant SWI/MRA, a
side-by-side diagnostic comparison, correct anatomy labels, and a thorough
PC / mobile / screen-reader accessibility overhaul.

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
- **Easier, more accessible controls (PC & mobile).** Sliders have a larger,
  easier-to-grab thumb that **grows further on touch devices** (bigger tap targets
  for buttons and checkboxes too), and every control shows a clear **keyboard focus
  ring**. Each parameter slider now announces a proper **screen-reader name and
  spoken value-with-unit** (e.g. "Repetition time TR, 500 milliseconds"), toggle
  groups report their pressed state, and the main regions are labelled landmarks.
  Narrow layouts use larger, more legible type.
- **Accessible dialogs, announcements and reduced motion.** The intro and lesson
  pickers are proper labelled **modal dialogs** — focus moves into them on open,
  returns to the trigger on close, and **Escape** dismisses them. Dynamic readouts
  (measurement results, the A/B compare delta, status/hint lines, the active lesson
  step and sequence blurb) are **live regions** so screen-reader users hear them.
  The build now honours **`prefers-reduced-motion`**, dropping the splash-bar fill,
  busy fade and transitions.

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
