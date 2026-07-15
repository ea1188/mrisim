# Course physics diagrams — batch 3 design

Date: 2026-07-15
Status: approved (design), building

## Goal

Two more course diagrams that need new (non-curve) drawing primitives, reusing the
batch 1/2 `window.CourseDiagrams` mounting: a **SNR / scan-time trade-off** calculator
(HTML/CSS bars) and a **k-space center-vs-periphery** widget with *real* inverse-FFT
reconstruction on a synthetic phantom (canvas).

## Reuse / context

- Batch 1/2 shipped `course_diagrams_math.js` (UMD, node-tested) + `course_diagrams.js`
  (renderer with `BUILDERS` + `attach`) + wiring (course.html scripts/CSS, course.js hook,
  sw.js, eslint). Batch 3 adds no new files and no new wiring; only new builders, math,
  two `DIAGRAM_MAP` keys, and CSS.
- **Invariant:** every `DIAGRAM_MAP` key MUST be a real `kind:"education"` `body.title`
  (guard test enforces). Both new keys verified real education titles.

## Decisions (approved)

- Build **both** widgets this batch.
- k-space: **real reconstruction** (canvas + a small FFT), not a schematic grid.
- k-space controls: **three preset buttons** (Center / Edges / Full), no radius slider.
- Phantom: **a disc + a couple of sharp bars** (contrast + detail).

## New math (`course_diagrams_math.js`, all pure + unit-tested)

- `fft1d(re, im, inverse)` — in-place radix-2 Cooley-Tukey FFT; length a power of 2;
  inverse pass divides by N.
- `fft2d(re, im, N, inverse)` — 2D transform of an N×N row-major complex array by
  applying `fft1d` to rows then columns.
- `fftshift2d(a, N)` — swaps diagonal quadrants (moves DC to center); its own inverse for
  even N.
- `snrScanRel({slice, matrix, nex, bw})` → `{ snr, time }` relative multipliers vs the
  baseline `{slice:3, matrix:192, nex:1, bw:32}`:
  - `snr = (slice/3)·(192/matrix)²·√(nex/1)·√(32/bw)`
  - `time = (matrix/192)·(nex/1)`

Tests: `fft1d` delta→constant + inverse round-trip + constant→DC spike; `fft2d` round-trips
an image; `fftshift2d` self-inverse and moves DC to center; `snrScanRel` baseline=1×, thick
slice ×2 SNR, fine matrix ×0.25 SNR / ×2 time, NEX 4 ×2 SNR.

## Widget: SNR / scan-time trade-offs → *Image quality: SNR, CNR, resolution & the trade-offs*

- Two horizontal **bars** (plain HTML `div`s, not SVG — the SVG `svgEl` helper is scoped
  inside `makePlot`): relative **SNR** and relative **scan time**, each scaled against a
  baseline tick at 1.0 (display capped at 3×; fill turns `--warn` when below 1×).
- Preset rows (grouped `.diag-<key>` buttons, one `.on` at a time per group): Slice
  (Thin 3 / Thick 6), Matrix (Coarse 192 / Fine 384), NEX (1/2/4), BW (Low 32 / High 64).
- Readout names the trade-off. No canvas, no `makePlot`.

## Widget: k-space reconstruction → *Data acquisition: k-space, encoding and the Fourier transform*

- 64×64 synthetic phantom generated in JS (disc + sharp bars; no external assets — CSP-safe).
- Forward `fft2d` once; `fftshift2d` to center DC. On each preset: copy the centered
  spectrum, zero the unkept region (Center keeps radius ≤ R≈0.12·N; Edges zeros that center;
  Full keeps all), draw the k-space magnitude (log-scaled, kept region outlined in `--accent`)
  on one `<canvas>`, then `fftshift2d` back + inverse `fft2d` and draw the magnitude image on
  a second `<canvas>`. Center-only returns blurred-but-full-contrast; edges-only returns
  outlines with no contrast.
- Two 64×64 canvases CSS-scaled to ~140px with `image-rendering: pixelated`. No animation
  (reduced-motion irrelevant).

## CSS additions (`web/course.html`)
- Bars: `.diag-bar-row`, `.diag-bar-label`, `.diag-bar-track`, `.diag-bar-fill`
  (`.low` variant), `.diag-bar-base`.
- Canvas: `.diag-kspace`, `.diag-canvas-wrap`, `.diag-canvas`, `.diag-canvas-cap`.
- Bar-fill width transition goes in the existing `@media (prefers-reduced-motion:
  no-preference)` block.

## DIAGRAM_MAP additions
```
"Image quality: SNR, CNR, resolution & the trade-offs": ["snr-tradeoff"],
"Data acquisition: k-space, encoding and the Fourier transform": ["kspace-recon"],
```

## Verification
- `npm run test:web` (FFT round-trip + shift + SNR tests, guard test covers 2 new keys),
  `npm run lint`, `ruff check src/ tests/`.
- Canvas prototype via Artifact (canvas is allowed; phantom is generated, no external asset).
- Branch → PR → gate-merge. No DB change. No `Co-Authored-By`.

## Risks
- FFT correctness → covered by round-trip unit tests.
- Performance: 64×64 via 1D FFTs is ~microseconds; one inverse transform per click is instant.
- Canvas is a new render path in an SVG-centric file → isolated to the one k-space builder.

## Out of scope (YAGNI)
- Draggable k-space cutoff radius; brain-like phantom; DWI/other new physics (done in batch 2).
