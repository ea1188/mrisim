# Course content: MR parameters & image quality (PDF phase 4) — Design

**Goal:** Add MR-parameter content to the paid course — three reading lessons plus ~24 quiz items —
generalized from the "MR Parameters" staff deck (the parameter to SNR / scan-time / resolution
tradeoffs, the acquisition parameters and k-space techniques, and how TR/TE/TI/flip angle set image
contrast). This is **PDF phase 4**, following phase 1 (contrast reactions, #392), phase 2 (clinical
protocols by region, #393-#397), and phase 3 (coil selection & positioning, #398).

**Status:** Approved 2026-07-08. Topic split ("3 lessons, all three topics") chosen by the user. See
[[project_pdf_content_phases]].

## Context

Content lives in `data/course_content.json` (source; seeded to Supabase `course_content`, served by
`web/course.js`). This deck is fundamentally about image quality and acquisition, so it spans three
existing, already-mapped topics. **No `course.js` change** (all three are already in `TOPIC_CFG`):

- `image-quality` — Modules 5 "Image quality & speed" and 6 "How the image is built" (the SNR to
  scan-time to resolution tradeoffs, bandwidth, voxel and SNR relationships).
- `data-acquisition` — Module 6 "How the image is built" (matrix, FOV, NEX, phase resolution, partial
  Fourier, oversampling, parallel imaging, k-space, scan-time formula).
- `contrast-weighting` — Module 2 "Where contrast comes from" (TR/TE/TI and flip angle set T1/T2/PD/
  FLAIR/STIR weighting; Ernst angle; sequence-specific flip-angle ranges).

Item shape `{topic, kind, ord, body}`; education `body` = `{title, html, keypoints, worked_example,
memory_hooks, exam_traps}`; quiz `body` = `{prompt, options[4], answer (0-idx), explain}`. Answer-length
guard forbids a keyed answer exceeding every distractor by >20%. All quiz keyed to index 0 (course.js
shuffles at render, so not a tell). ~24 quiz split 8 image-quality / 8 data-acquisition / 8
contrast-weighting.

## Source & generalization

Source: `pdf education/MR Parameters 2026.pdf` (63 pages). Generalize: named presenter and courtesy
credits removed; vendor terms (IPAT, GRAPPA, VIBE, MPRAGE) replaced with the generic mechanism
("parallel imaging", "3D gradient echo") while keeping the physics; vendor channel-count examples
(8ch vs 15ch) kept only as generic illustration ("more coil elements"), never as a board fact. Keep the
physics terms (SNR, TR, TE, TI, flip angle, Ernst angle, NEX/signal averages, FOV, matrix/base
resolution, phase resolution, FOV phase, slice thickness, distance factor/slice gap, partial Fourier,
oversampling, receiver bandwidth, chemical shift, k-space, parallel imaging) as standard.

Kept as generally true (physics/ARRT-consistent), from the deck's master tradeoff table:

- **SNR controlling factors:** SNR = mean signal / noise SD. Fixed: field strength, sequence design,
  tissue. Operator-controlled: voxel size, TR/TE, signal averages (NEX), receiver bandwidth, coil.
  Higher field, more coil elements, longer TR, shorter TE, higher flip angle (to a point), more NEX,
  larger voxel (bigger FOV / smaller matrix / thicker slice) all raise SNR.
- **Master tradeoff directions** (increase the parameter): TR up -> SNR up, time up; TE up -> SNR down
  (minor); flip angle up -> SNR up; NEX up -> SNR up, time up; FOV up -> SNR up, resolution down;
  matrix up -> SNR down, time up, resolution up; slice thickness up -> SNR up, fewer slices, resolution
  down; FOV phase up -> SNR up, time up, coverage without changing resolution; oversampling up -> SNR up,
  time up; parallel imaging up -> SNR down, time down, aliasing artifact; ETL up -> SNR down, time down,
  more SAR; bandwidth up -> SNR down, time down (shorter min TR), less chemical shift and metal
  susceptibility.
- **Scan time (2D spin echo):** time = TR x NEX x number of phase-encoding steps. NEX doubling gains
  ~40% SNR (sqrt(2), because noise is re-sampled too) and doubles time; it also reduces motion and
  pulsatile-flow artifact.
- **TR/TE and contrast:** TR is time between excitations (affects number of slices and scan time); TE is
  time to echo where data is collected (affects contrast); each echo fills one phase-encode line of
  k-space. Weighting: T1 short TR / short TE; T2 long TR / long TE; PD long TR / short TE; FLAIR long TR
  / long TE with a long inversion time to null CSF; STIR short TI to null fat.
- **Flip angle:** the excitation angle tipping protons from B0. Ernst angle gives max SNR for a given
  TR. Spin/turbo spin echo use 90 to 180; gradient echo uses less than 90; inversion recovery uses an
  initial 180 then 90 (then 180 for the echo).
- **Resolution:** voxel = FOV/matrix (in-plane) by slice thickness. Smaller voxel = higher resolution,
  lower SNR. Phase resolution is a percent reduction of phase pixels (rectangular voxels); frequency
  resolution set by base resolution; slice resolution set by slice thickness (percent only on 3D).
  Partial Fourier acquires part of k-space for faster scans (possible blurring, lower SNR). FOV phase
  changes phase-direction coverage without changing resolution.
- **Slice thickness and gap:** thicker slices raise SNR, cover with fewer slices, lower resolution.
  Distance factor (slice gap) is a percent of thickness; it reduces cross-talk and slices needed but can
  skip small pathology.
- **Oversampling:** acquires data beyond the FOV to suppress phase (or slice, on 3D) aliasing / wrap;
  raises SNR and time.
- **Parallel imaging:** undersamples k-space using multi-coil sensitivity to cut scan time; lowers SNR
  (roughly by the square root of the acceleration factor) and can leave central aliasing artifact if the
  FOV is too small.
- **Bandwidth:** range of frequencies sampled in readout; higher bandwidth lowers SNR but shortens the
  minimum TR and reduces chemical-shift and metal-susceptibility artifact.

## Content to add

1. **Lesson 1 — "MR image quality: SNR, scan time, and spatial resolution tradeoffs"** —
   `{topic:"image-quality", kind:"education"}`, all six body fields. What SNR is and its fixed vs
   operator-controlled factors; the master parameter table read as tradeoffs (SNR vs time vs resolution);
   voxel size as the central lever; receiver bandwidth and chemical shift. exam_traps: raising matrix
   improves resolution but lowers SNR and lengthens the scan; higher bandwidth lowers SNR but cuts
   chemical shift and shortens minimum TR.
2. **Lesson 2 — "Acquisition parameters and k-space: matrix, FOV, NEX, and acceleration"** —
   `{topic:"data-acquisition", kind:"education"}`, all six body fields. Matrix/base resolution, FOV and
   FOV phase, NEX and the scan-time formula (TR x NEX x phase steps), phase resolution, slice thickness
   and distance factor, partial Fourier, oversampling, and parallel imaging; how each fills or
   undersamples k-space. exam_traps: NEX doubling gains ~40% SNR (sqrt 2), not double, and doubles time;
   parallel imaging cuts time at the cost of SNR and can leave central aliasing.
3. **Lesson 3 — "TR, TE, TI, and flip angle: setting image contrast"** —
   `{topic:"contrast-weighting", kind:"education"}`, all six body fields. TR and TE roles; the T1/T2/PD/
   FLAIR/STIR TR-TE-TI pattern; flip angle and the Ernst angle; flip-angle ranges by sequence family
   (spin echo 90 to 180, gradient echo under 90, inversion recovery 180 then 90). exam_traps: PD is long
   TR with short TE (not long TE); FLAIR and STIR both null a tissue via TI but FLAIR uses a long TI for
   CSF while STIR uses a short TI for fat.
4. **~24 quiz items** split 8 `image-quality` (SNR definition; fixed vs controllable factors; a
   tradeoff-table direction such as TR up or matrix up; bandwidth vs chemical shift and SNR; voxel-SNR;
   thicker slice tradeoff) + 8 `data-acquisition` (scan-time formula; NEX SNR/time; matrix vs FOV on
   voxel size; phase resolution; partial Fourier; oversampling vs wrap; parallel imaging SNR/time/
   artifact; FOV phase coverage) + 8 `contrast-weighting` (TR vs TE roles; T1/T2/PD/FLAIR/STIR TR-TE-TI;
   flip angle and Ernst angle; sequence flip-angle ranges; TI nulling fat vs CSF). Four balanced-length
   options, no em dashes, no AI tells.

Voice per [[feedback_no_ai_tells_content]].

## Integration, testing, edge cases

Same pipeline as phases 2-3: Fable author writes `{lessons:[3], quiz:[~24]}` -> Fable accuracy review
(physics-correct, fully generalized, plausible distractors, balanced lengths, no dashes) -> controller
appends to `data/course_content.json` (fresh ords after global max, byte-stable `quiz_length_tools.dump`)
-> bump `tests/test_course_depth.py` count 30 -> 33 -> guard + depth + images tests green + `ruff check
src/ tests/` -> idempotent MCP reseed by `body->>'title'`/`prompt`. No JS/engine change. Branch off fresh
main after #398 (phase-3 coil/positioning) merges so the baseline is 401 items / depth 30. Edge cases:
answer-length tell (guard), duplicate prompt/title (applier + reseed not-exists guard), generalization
miss (accuracy reviewer), depth-count drift (bump the two `30`s to `33`).

## Out of scope

- Any `course.js` / curriculum-map change (all three topics already mapped).
- Image-based questions (text only here).
- Vendor QA / protocol-update deck pages and vendor product names (IPAT/GRAPPA/VIBE/MPRAGE) as such.
- Deep k-space theory beyond how parameters fill or undersample it (existing physics modules cover the
  rest).
