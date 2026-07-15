# Course physics diagrams — batch 4 design

Date: 2026-07-15
Status: approved (design), building

## Goal

Four advanced-imaging diagrams that deepen existing modules, reusing the batch 1-3 engine:
parallel imaging (canvas+FFT), k-space trajectories (SVG scatter), chemical shift / Dixon
(curve), and Gibbs ringing (canvas+FFT). Brings the course to 13 interactive diagrams.

## Reuse / context

- `course_diagrams_math.js` (UMD, node-tested) has `fft1d`/`fft2d`/`fftshift2d`, `makePlot`
  helpers, `sample`, curve/canvas patterns. `course_diagrams.js` has the `BUILDERS` registry +
  `attach`. Wiring (scripts/course.js/sw.js/eslint) already covers `course_diagrams*.js`.
- **Invariant:** every `DIAGRAM_MAP` key MUST be a real `kind:"education"` `body.title`
  (guard test). All four homes verified.

## Decisions (approved)

- Build all four. Parallel imaging shows the aliasing that acceleration causes and that coils
  unfold; it does NOT simulate the multi-coil SENSE/GRAPPA reconstruction (out of scope).
- Preset buttons (consistent). 1.5 T teaching approximations.

## New math (`course_diagrams_math.js`, unit-tested)

- `fatWaterSignal(teMs, fatFrac, deltaFHz)` = `|(1-fatFrac) + fatFrac·e^(-i·2π·deltaF·TE_s)|`.
  Tests: TE=0 → 1 (in phase); opposed TE `1000/(2·deltaF)` → `|1-2·fatFrac|`; in-phase TE
  `1000/deltaF` → 1.

## Engine tweak (`course_diagrams.js`)

- Hoist the tiny `svgEl(name, attrs)` helper out of `makePlot` to module scope (next to `el`)
  so a non-plot SVG widget (trajectories) can build SVG. `makePlot` keeps calling it via closure;
  backward-compatible (pure relocation).

## Widgets

### Parallel imaging → *Acquisition parameters and k-space: matrix, FOV, NEX, and acceleration*
- Reuse the 64×64 phantom + cached forward FFT + `fftshift2d` (as `kspace-recon`). Presets
  Full / R=2 / R=3: keep every Rth centered phase-encode row (`(ky - N/2) % R === 0`), zero the
  rest → the reconstruction aliases (FOV/R in phase, image wraps). Two canvases (k-space + image);
  readout names R and the wrap. Caption: coils unfold the aliasing (not simulated here).

### k-space trajectories → *Spatial encoding: slice, phase, and frequency gradients into k-space*
- SVG scatter of sample points, presets Cartesian / Radial / Spiral. Cartesian = a coarse dot
  grid (line by line); Radial = spokes through center; Spiral = an Archimedean spiral. Caption:
  radial/spiral oversample the center and tolerate motion (non-Cartesian). New CSS `.diag-kpt`.

### Chemical shift / Dixon → *Fat suppression: STIR, spectral, Dixon and water excitation*
- Curve of `fatWaterSignal` vs TE (0-10 ms, `deltaF`=220 Hz), markers at opposed-phase
  (~2.3 ms) and in-phase (~4.6 ms); fat-fraction presets (10/30/50%). Co-located with the
  existing `ir-nulling` widget in this card (map value becomes `["ir-nulling","chemical-shift"]`).

### Gibbs ringing → *MR image quality: SNR, scan time, and spatial resolution tradeoffs*
- 64×64 phantom with a strong sharp-edged bright square; cached forward FFT + shift. Presets
  64 / 32 / 16: keep a central `keep×keep` block of k-space, zero the rest → edges blur and
  ringing lines appear. Two canvases (k-space + image); readout ties matrix to ringing.

## DIAGRAM_MAP additions / change
```
"Acquisition parameters and k-space: matrix, FOV, NEX, and acceleration": ["parallel-imaging"],
"Spatial encoding: slice, phase, and frequency gradients into k-space": ["kspace-trajectories"],
"Fat suppression: STIR, spectral, Dixon and water excitation": ["ir-nulling", "chemical-shift"],  // add chemical-shift
"MR image quality: SNR, scan time, and spatial resolution tradeoffs": ["gibbs-ringing"],
```

## CSS additions (`web/course.html`)
- `.diag-kpt { fill: var(--accent); }` (trajectory sample dots). Canvas widgets reuse the
  existing `.diag-kspace`/`.diag-canvas`/`.diag-canvas-wrap`/`.diag-canvas-cap` from batch 3.

## Verification
- `npm run test:web` (fatWaterSignal + guard test covers 4 new keys), `npm run lint`,
  `ruff check src/ tests/`.
- Canvas + SVG prototype via Artifact (all 13 widgets).
- Branch → PR → gate-merge. No DB change. No `Co-Authored-By`.

## Out of scope (YAGNI)
- Multi-coil SENSE/GRAPPA unfold; real non-Cartesian gridding reconstruction; new education content.
