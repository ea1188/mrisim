# MRI signal-chain animation (`signal-chain`) — design

**Goal:** An interactive, step-through animation that walks a learner through the entire MRI
signal-generation chain, from protons aligning in B0 all the way to a reconstructed image.

**Where it lives:** a new diagram widget on the education card
`"The image-formation pipeline: excite, encode, sample, reconstruct"` (module "How the image is
built"), which currently has no diagram. `DIAGRAM_MAP["The image-formation pipeline: excite, encode,
sample, reconstruct"] = ["signal-chain"]`.

**Approach:** SVG vector graphics animated by one `requestAnimationFrame` loop (the existing widget
idiom: `svgEl`, module-scope helpers, the `reduceMotion` flag), for stages 1-6; **reuse the existing
canvas FFT helpers** (`phantom`, `centeredSpectrum`, `drawKMag`, `drawIMag`, `reconMag`) already in
`web/course_diagrams.js` for stages 7-9 (k-space / FFT / image). Mixing SVG and canvas already exists
in the file (the k-space widgets).

## Component

One builder `function buildSignalChain()` in `web/course_diagrams.js`, inserted before
`var BUILDERS = {`, registered in `BUILDERS` as `"signal-chain": buildSignalChain`. It is a small
**stage machine**:

```
var STAGES = [ { label, caption, kind: "svg"|"canvas", draw(ctxOrG, t) }, ... ]  // 9 entries
```

- `state = { i: 0, playing: false }` — current stage index.
- A single rAF loop advances an animation clock `t` and calls the current stage's `draw(t)`.
- One rendering `<svg>` (viewBox 0 0 340 200) for the SVG stages and one `<canvas>` (64x64 upscaled
  via CSS, like the k-space widgets) for the canvas stages; show whichever the current stage uses,
  hide the other (`display`).
- A caption `div.diag-readout`, a stage-chip row, and a controls row.

## The 9 stages

Each `draw(t)` renders that stage at clock `t` (seconds, looping). Coordinates are schematic.

1. **Protons align (parallel/antiparallel in B0).** A ~5x4 grid of short spin arrows. A slight
   majority point up (parallel, low energy) and the rest down (antiparallel); each arrowhead traces a
   small circle (precession wobble) as `t` advances. A vertical B0 arrow with label on the left.
   Caption: protons align with or against B0; slightly more align parallel (lower energy).
2. **Net magnetization M0.** The grid arrows fade to faint; their vector sum resolves into one bold
   longitudinal vector **M0** along +z (up). Animate the individual arrows shrinking/fading while M0
   grows in. Caption: the small parallel excess sums to a net longitudinal magnetization M0 along B0.
3. **RF pulse tips M into the transverse plane.** A small "RF" burst indicator (a short oscillation
   near the coil), and the M0 vector spirals from +z down to the transverse (xy) plane over the
   stage's loop (a 90 degree flip), tracing a helix. Caption: an RF pulse at the Larmor frequency tips
   M into the transverse plane where it can be detected.
4. **Precession + FID (T2* decay).** The transverse vector rotates in the plane at a steady rate while
   its length shrinks (dephasing). Beside it, a decaying sinusoid (the free induction decay) draws out
   synchronized to the rotation. Caption: the transverse magnetization precesses at the Larmor
   frequency and decays (T2*), inducing the free induction decay.
5. **Coil detects the signal.** A receiver-coil symbol; the rotating transverse component induces an
   oscillating voltage shown as a live trace on the coil. Caption: the changing transverse
   magnetization induces an oscillating voltage in the receiver coil, the raw MR signal.
6. **Spatial encoding (slice / phase / frequency gradients).** A row of ~8 spins; a gradient "blip"
   sweeps and winds their phase linearly across space (a phase ramp), i.e., position is encoded into
   phase/frequency. Small labels Gz/Gy/Gx. Caption: slice, phase, and frequency gradients encode each
   voxel's position into the signal's phase and frequency.
7. **Signal fills k-space.** Canvas: the k-space magnitude image fills in line by line, center-out
   (reuse `phantom(N)`, `centeredSpectrum`, `drawKMag`), animating rows appearing over the loop.
   Caption: the encoded samples fill k-space; the center holds contrast, the edges hold fine detail.
8. **2D Fourier transform.** Canvas: a brief transition from the k-space magnitude to the image
   (reuse `reconMag`/`drawIMag`), e.g., a wipe or crossfade. Caption: a two-dimensional Fourier
   transform converts k-space into the final image.
9. **Image.** Canvas: the final reconstructed phantom image, steady. Caption: one-line recap, the same
   chain from aligned protons to signal to k-space to image.

## Interaction

- **Stage chips:** a `.diag-controls` row of 9 small `.diag-btn`s labeled `1 Align`, `2 Net M`,
  `3 RF`, `4 FID`, `5 Detect`, `6 Encode`, `7 k-space`, `8 FFT`, `9 Image`; clicking jumps to that
  stage. The current one gets the `on` class.
- **Prev / Next:** two `.diag-btn`s and a `Stage N of 9` label between them.
- **Play / Pause:** a `.diag-btn` toggling `state.playing`; while playing, each stage plays its loop
  for a fixed dwell (about 3.5 s) then auto-advances; pressing Pause (or reaching stage 9) stops.
  Matches the existing Play pattern on `t1-recovery`/`ir-nulling`.
- The caption updates to the current stage's text.

## Reduced motion

If `reduceMotion` is true: no rAF loop; each stage's `draw` is called once at its representative
end-state `t` (a static frame), and Play advances stages instantly on a short timer or is disabled in
favor of the chips/Prev/Next. Same policy as the other widgets.

## Constraints

- No em dashes in any caption/label text. US spelling.
- Schematic, not a Bloch simulation. One-screen-tall like the other widgets.
- Reuse existing helpers; do not duplicate the FFT/phantom code.
- The `DIAGRAM_MAP` key must be the exact education-card title (guarded).

## Testing

- `web/course_diagrams_math.test.mjs`: add `assert.deepEqual(DIAGRAM_MAP["The image-formation
  pipeline: excite, encode, sample, reconstruct"], ["signal-chain"]);` and insert `"signal-chain"`
  into the sorted `ids` array. Run `node --test` (all pass) and `npx eslint web/course_diagrams*.js`
  (clean).
- Browser render-check: extend the harness to build the widget, click through all 9 stages without
  error, and screenshot several stages for a visual accuracy pass (the same render + visual review
  used on the other 45 diagrams).

## Out of scope (YAGNI)

No audio, no draggable timeline (step-through chosen), no per-tissue parameters, no exact physics.
T1/T2/k-space/FFT specifics already have dedicated widgets; this is the end-to-end pipeline overview.
