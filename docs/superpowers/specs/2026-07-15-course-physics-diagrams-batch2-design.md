# Course physics diagrams — batch 2 design

Date: 2026-07-15
Status: approved (design), building

## Goal

Add three more interactive SVG diagrams to the guided course, reusing the batch 1
engine (`makePlot`, `window.CourseDiagrams`): the Ernst angle, inversion-recovery
nulling (STIR / FLAIR), and DWI signal vs b-value. Each mounts inside an existing
`kind:"education"` card.

## Reuse / context (batch 1, PR #438)

- Pure physics in `web/course_diagrams_math.js` (UMD, node-tested); SVG renderer in
  `web/course_diagrams.js` with shared `makePlot()` and a `BUILDERS` registry;
  `attach(card, eduTitle)` mounts widgets by `DIAGRAM_MAP` title. All wiring
  (`course.html` scripts/CSS, `course.js` hook, `sw.js`, `eslint.config.mjs`) already
  exists — batch 2 adds no new files and no new wiring.
- **Invariant:** every `DIAGRAM_MAP` key MUST be a real `kind:"education"` `body.title`
  in `data/course_content.json`; the guard test enforces it. The three new keys are
  verified real education titles.

## Decisions (from brainstorming, approved)

- Three curve-native widgets; same conventions as batch 1 (preset buttons, tissue
  selectors, ▸ Play sweep where a single curve animates, reduced-motion static paint,
  theme tokens, 1.5 T teaching approximations, no read-tracking change, no em dashes).
- **DWI y-axis: linear** (not semilog).
- **Ernst widget: tissue selector + TR presets** (not a single fixed tissue).

## Math module additions (all pure, unit-tested)

| Function | Definition |
|---|---|
| `ernstAngle(TR, T1)` | `acos(e^(−TR/T1))` — radians |
| `spoiledGreSignal(alpha, TR, T1)` | `sin α·(1−E1)/(1−cos α·E1)`, `E1 = e^(−TR/T1)`; `alpha` in radians |
| `irMz(t, T1)` | `1 − 2·e^(−t/T1)` |
| `nullTI(T1)` | `T1·ln2` |
| `dwiSignal(b, ADC)` | `e^(−b·ADC)` |

New data table `ADCS` (mm²/s, 1.5 T teaching approximations):
`[{ id:"restricted", label:"Restricted (stroke)", adc:0.0006 }, { id:"normal", label:"Normal tissue", adc:0.0010 }, { id:"free", label:"Free water (CSF)", adc:0.0030 }]`.

Unit tests: Ernst angle at TR=T1 equals `acos(1/e)`; `spoiledGreSignal` is maximized at
`ernstAngle` (spot-check the peak); `irMz(0)=−1`, `irMz(nullTI(T1))≈0`, `irMz(∞)→1`;
`dwiSignal(0,ADC)=1`, higher ADC decays faster, restricted stays brighter at b=1000.

## Engine tweak to `makePlot` (backward compatible)

- Add `opts.yMin` (default `0`). `toY(v) = y0 − (y0−y1)·(v−yMin)/(yMax−yMin)`. With
  `yMin=0` every existing widget is unchanged.
- When `opts.yMin < 0`, draw a faint horizontal **zero line** at `toY(0)` across the
  plot (class `diag-axis`). The bottom axis, x ticks and x labels stay at the frame
  bottom (`y0`); only this reference line is added. The y-tick loop already handles
  negative values, so passing `yTicks:[-1,-0.5,0,0.5,1]` labels them.

## The three widgets

### Ernst angle → *Flip angle: the Ernst angle and the SAR trade-off*
- Plot: signal (`spoiledGreSignal`) vs flip angle 0–90° (x in degrees, converted to
  radians inside the sampler), `xTicks:[0,30,60,90]`, yMax 1.
- Controls: tissue `<select>` (fat/WM/GM/CSF) + TR presets (Short 150, Medium 500,
  Long 1500 ms). ▸ Play sweeps the curve.
- Marker at the Ernst angle (degrees). Readout: "Ernst angle = X° for TR … / T1 … ;
  above it, more signal costs SAR for little gain." Caption notes the SAR trade-off.

### Inversion-recovery nulling → *Fat suppression: STIR, spectral, Dixon and water excitation*
- Plot: `irMz` for fat, white matter, CSF over t (`xMax` 3000, `xTicks:[0,1000,2000,3000]`),
  `yMin:-1`, `yMax:1`, `yTicks:[-1,-0.5,0,0.5,1]`; zero line drawn. Fat = accent,
  WM = muted (`pd`), CSF = warn (`alt`). Caption maps the colors.
- Controls: TI presets computed from the model — "STIR (null fat)" = `round(nullTI(fat.T1))`,
  "FLAIR (null CSF)" = `round(nullTI(csf.T1))`. Marker at TI.
- Readout: "At TI = X ms, <tissue> is nulled" (tissue whose `|irMz(TI,T1)|` is smallest).

### DWI vs b-value → *Diffusion in disease: stroke, abscess and cellular tumors*
- Plot: `dwiSignal` for restricted / normal / free water over b (`xMax` 1000,
  `xTicks:[0,250,500,750,1000]`), linear yMax 1. Same 3-color scheme + caption legend.
- Controls: b presets (0, 500, 1000 s/mm²). Marker at b.
- Readout: signal remaining for each ADC at the chosen b; note restricted stays bright
  at high b (the DWI stroke sign).

## CSS additions (`web/course.html`)
- Re-add `.diag-curve.alt { stroke: var(--warn); }` (a third curve color; was removed in
  batch 1 when its only user went away — now three-curve widgets need it).
- No other CSS; `.env`, `.pd`, `.diag-dot`, markers already exist.

## DIAGRAM_MAP additions
```
"Flip angle: the Ernst angle and the SAR trade-off": ["ernst-angle"],
"Fat suppression: STIR, spectral, Dixon and water excitation": ["ir-nulling"],
"Diffusion in disease: stroke, abscess and cellular tumors": ["dwi-bvalue"],
```

## Verification
- `npm run test:web` (new math tests + the guard test auto-covers the 3 new keys),
  `npm run lint`, `ruff check src/ tests/` all green.
- Standalone Artifact prototype of the three new widgets (+ existing four) to click
  through before merge.
- Branch → PR → gate-merge. No DB change. No `Co-Authored-By`.

## Out of scope (YAGNI)
- SNR trade-off calculator and k-space grid (need new non-curve primitives — separate batch).
- Semilog DWI axis (chose linear).
