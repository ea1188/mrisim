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

## The stages (as shipped: 13, evolved from the original 9 through review)

The original 9-stage sketch was expanded during iterative review into **13 stages**. Two structural
decisions drove the change: (a) the whole encode/reconstruct half runs on **one real little picture**
(a generated smiley + its actual k-space, built once via `centeredSpectrum(OBJ.img)` and
reconstructed with `reconMag`) so nothing is abstract; (b) the "columns spin -> 2D k-space" leap is
decompressed into its real physics — slice select (Gz), frequency encode (Gx / readout, kx), and
phase encode (Gy, ky) as separate steps. A second canvas shows the image reconstructing live beside
k-space.

**Signal physics (single voxel):** 1 Align, 2 Net M (M0 grows at a shared pivot), 3 RF (M spirals
into the transverse plane), 4 FID (transverse precesses + decays T2* = the coil's induced voltage,
while Mz recovers to M0, T1 — the vector spirals back up).

**Imaging (the real picture):** 5 Object (a 3D body — stacked slices — millions of voxels each doing
1-4); 6 Slice (RF+Gz excite one 2D slice, the smiley); 7 Encode (Gx makes each column of the slice
precess at its own frequency); 8 Signal (the whole slice feeds one coil = one signal, explicitly the
FID from step 4 with the readout gradient on); 9 Readout (sampling sweeps across one horizontal line
of k-space, kx, bright center = contrast / faint edges = detail); 10 Phase (Gy picks which horizontal
line, ky); 11 k-space (repeat readout x phase fills the 2D grid, image reconstructs live center-out);
12 Detail (center-only reconstruction = blurry contrast vs edges-only = outlines); 13 Image (the same
smiley recovered).

Stages 1-10 are SVG (`svgEl`, the shared pivot/plane helpers, an inlined object `<image>` from
`OBJ.url`); 11-13 are canvas (two side-by-side canvases: `kOff`/masked-k-space + `reconMag`).

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
