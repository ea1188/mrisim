# Voxel Model v2: Mixel Partial Volume + Property-Level Texture

**Date:** 2026-09-01
**Status:** Draft for review
**Depends on:** the region-densification arc (#524–#530)

## Goal

Upgrade the per-voxel model from "one label × one multiplicative texture number"
to what a real voxel is: a **two-tissue mixture** whose components carry
**slightly individual properties**:

```
signal(voxel) = f · S(T1_a·δ, T2_a·δ, PD_a·δ)  +  (1−f) · S(T1_b, T2_b, PD_b)
```

where `a` is the dominant tissue, `b` the second tissue at a boundary, `f` the
dominant fraction, and `δ` the per-voxel detail modulation derived from the real
MRI (replacing today's post-hoc signal multiplication). Interior voxels have
`f = 1` and reduce to the current model. Payoff: tissue boundaries, cartilage,
and small structures render like real acquisitions; intra-tissue detail responds
correctly to sequence changes (a bright-on-T2 speck stays physically consistent
on T1) instead of being sequence-independent.

Decision taken: **two-tissue mixel**, not full BrainWeb-style fuzzy volumes.
Three-tissue junctions are rare; mixel costs ~2× atlas size and keeps the render
math a single lerp.

## Data contract

Per region, one new sidecar next to the existing atlas + texture:

- `mixel.npy` — uint8, shape `(2, Z, Y, X)`:
  - channel 0: second-tissue label id (0 where the voxel is pure)
  - channel 1: dominant fraction `f` encoded as `round((f − 0.5) * 510)`,
    so 255 = pure, 0 = 50/50. Interiors are (0, 255) — near-constant planes
    that gzip to almost nothing over the wire.
- Cache/bundle names follow the existing pattern: `mixel_iso_adapt_256.npy`
  for TotalSegMRI subjects, `data/<region>/mixel.npy` for SPIDER/knee,
  `web/data/regions/<Region>_mixel.npy` in the deploy bundle.
- **Absent file = current behavior.** Every consumer treats the sidecar as
  optional forever; that is the backward-compatibility story and the rollout
  lever.

## Producing fractions (build pipelines)

The honest source of sub-voxel information is the **higher-resolution grid the
pipelines already pass through** before their final resample (TotalSegMRI
native → iso≤256; SPIDER native → 1.3 mm; knee 512 → 256). New shared helper in
`nifti_region.py`:

- `mixel_from_labels(labels_hires, target_shape)` — for each candidate label,
  linearly resample its indicator to the target grid, then keep the top-2
  fractions per voxel. Offline cost: one zoom per present label (~16), fine.
- Where no higher-res stage exists, fall back to a σ≈0.5 indicator blur on the
  final grid (documented as synthetic).
- The knee script classifies *after* downsampling today; it keeps the blur
  fallback rather than reordering its pipeline in this project.
- Fractions are **geometric** (from resampling) in v2. Blending in k-means
  posterior softness is a possible v3; keeping argmax labels avoids re-litigating
  the classification work.

Orientation is the known dragon: every flip / `region_orient.straighten` /
crop applied to the atlas must apply identically to both mixel channels
(nearest for the label channel, nearest for the fraction channel). Guarded by
objective tests (below), not eyeballing.

## Engine integration

### Phase C — mixel rendering (contained chokepoint)

`rendering.partial_volume` already mixes per-label mean signals with fraction
maps — it just *synthesizes* the fractions by blurring at render time. The
mixel path replaces the synthesized fractions with the stored ones:

- `partial_volume_mixel(image, labels, second, f)`: per-label mean signals from
  the rendered image (as today), output `f·S_a + (1−f)·S_b` at boundary voxels,
  untouched interiors. All sequence implementations stay untouched — they keep
  producing the pure-tissue image, and mixing remains a post-step at the same
  place the synthetic PV runs today. When a region has no mixel sidecar, the
  existing synthetic path runs unchanged.
- Loaders (`web_adapter.load_region`, `app_regions`) gain an optional
  `mixel_3d`, sliced/reformatted alongside `phantom_3d` (audit every
  `phantom_3d` consumer: get_slice, oblique, acquire-3D reformat, scout).
- Later nicety (not in scope): the per-voxel fat-fraction maps from #528 can be
  refined by mixel fractions (a fat/muscle boundary voxel gets ff = f·0.0 +
  (1−f)·1.0 instead of binary).

### Phase B — property-level texture

New param `texture_mode: "signal" | "property"` (default `"signal"` until
validated):

- Property mode hooks the existing `param_maps` machinery: per-voxel
  `PD·tex`, `T2·(1 + 0.5(tex−1))`, `T1·(1 + 0.3(tex−1))` (coefficients to be
  calibrated so current T1w/T2w appearance is preserved), then the sequence
  signal is evaluated **vectorized per voxel** via the already-vectorizable
  `signal_engine` functions. The post-hoc signal multiplication is skipped in
  this mode (no double-dip).
- Scope of sequence coverage in v2: SE / GRE / IR / FSE main paths. Exotic
  paths (EPI, SWI, angiography, perfusion...) keep signal-texture and are
  documented as such; they migrate opportunistically later.

Performance budget: browser slice is 256²; the extra work is one lerp (mixel)
and vectorized exponentials (property mode) — sub-millisecond next to the
existing FFT work. No format change to `worker.js` payloads beyond one more
lazily-fetched `.npy` per region.

## Phasing (one PR each, full suite + QC renders per phase)

- **A. Pipelines emit mixel sidecars** — helper + all three build paths +
  regenerated data, shipped dormant (nothing reads them). Guards: fraction sums,
  boundary-only mixing, orientation centroid tests on the sidecars.
- **B. Property texture behind the flag** — default off; QC compares every
  main-path sequence against current renders; flip default on when calibrated.
- **C. Mixel render path** — replaces synthetic PV when the sidecar exists;
  QC zoomed boundary crops (disc/cord/endplate, cartilage) before/after;
  then enable everywhere.

## Testing

- Unit: `mixel_from_labels` (two-block phantom: boundary fractions correct and
  complementary, interiors pure); encode/decode round-trip of the fraction
  byte; `partial_volume_mixel` (boundary voxel = weighted mean of the two
  tissues' signals, interior untouched, absent-sidecar identity).
- Property mode: per-sequence contrast-ordering regression (WM/GM/CSF and
  fat/muscle/fluid orderings preserved); flag-off renders bit-identical to
  today.
- Data guards: mixel present for all regions, fraction stats sane (boundary
  fraction of body within measured bounds), orientation via label centroids.
- Perf smoke: render time within 10% of current in the browser worker.

## Risks

- Orientation/flip mismatches on the new channels (the sagittal-flip saga —
  mitigated by objective tests on the sidecars themselves).
- Lesson prerender and course-figure scripts slice regions too; they must pass
  mixel state through or explicitly opt out (they render at the same
  chokepoint, so opting in should be automatic — verify).
- Property-mode calibration drifting the look of the shipped presets; the flag
  + side-by-side QC is the control.
