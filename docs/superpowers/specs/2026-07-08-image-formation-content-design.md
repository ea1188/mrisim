# Course content: spatial encoding & image formation (PDF phase 6) — Design

**Goal:** Add spatial-encoding and image-formation content to the paid course — two reading lessons plus
~16 quiz items — from the "MR Basic Physics 2nd class" deck. This is **PDF phase 6, the final PDF phase**,
following phases 1-5 (#392, #393-#397, #398, #399, #400). After this phase the PDF program is complete and
work pivots to class-owner sub-project B.

**Status:** Approved 2026-07-08. Scope ("2 lessons, fuller treatment") chosen by the user. See
[[project_pdf_content_phases]].

## Context

Content lives in `data/course_content.json` (source; seeded to Supabase `course_content`, served by
`web/course.js`). Two existing, already-mapped topics. **No `course.js` change** (both are in
`TOPIC_CFG`):

- `data-acquisition` — Module 6 "How the image is built" (the three spatial-encoding gradients, k-space,
  Fourier transform).
- `pulse-sequences` — Module 6 "How the image is built" (the image-formation pipeline: excite, encode,
  sample, reconstruct, and where GRE / spin echo / inversion recovery sit in it).

Item shape `{topic, kind, ord, body}`; education `body` = `{title, html, keypoints, worked_example,
memory_hooks, exam_traps}`; quiz `body` = `{prompt, options[4], answer (0-idx), explain}`. Answer-length
guard forbids a keyed answer exceeding every distractor by >20%. All quiz keyed to index 0 (course.js
shuffles at render, so not a tell). ~16 quiz split 8 data-acquisition / 8 pulse-sequences.

**Overlap note (critical for authoring):** this is the last and most redundant deck. Phase 4 already
covers k-space *sampling* parameters (matrix, FOV, NEX, partial Fourier, parallel imaging) and TR/TE
weighting; phase 5 already covers the spin-echo 180 refocusing pulse, T2 vs T2*, and relaxation. This
phase must add only what is genuinely new:

- **Lesson 1 (data-acquisition)** = the *spatial-encoding chain*: how the three gradients localise signal
  and write it into k-space, then how the Fourier transform reconstructs the image. This is NOT the same
  as phase 4's k-space *sampling*; it is the encoding mechanism (which gradient does what, and why).
- **Lesson 2 (pulse-sequences)** = the *image-formation pipeline as a workflow* (excite, then spatially
  encode, then sample the echo, then reconstruct) and a *placement-level* recap of GRE vs spin echo vs
  inversion recovery: how each forms its echo and where it fits the pipeline. It must NOT re-teach the
  T2\*-refocusing detail (phase 5) or the TR/TE/TI weighting table (phase 4); it frames the sequences by
  echo-formation mechanism and role, not by weighting recipe.

Quiz prompts must not duplicate any existing prompt (applier + reseed guard on exact text; the author must
also avoid near-duplicates of existing phase 4/5 questions).

## Source & generalization

Source: `pdf education/MR Basic Physics 2nd class 2023.pdf` (23 pages, mostly diagram slides with heading-
only text). Editor/credit names and external URLs removed. Vendor-neutral physics; keep standard terms
(slice-select / phase-encode / frequency-encode gradients, k-space, Fourier transform, gradient echo,
spin echo, inversion recovery).

Kept as generally true (physics/ARRT-consistent):

- **Slice selection:** a slice-select gradient is applied along one axis (commonly z, head-foot for an
  axial slice) *during* the RF pulse; only the location where the local Larmor frequency matches the RF
  is excited. Slice thickness is set by the RF bandwidth and the gradient steepness.
- **Phase encoding:** after excitation, a phase-encode gradient is switched on briefly (commonly along
  the R-L axis) to give spins a position-dependent phase shift; it is stepped to a different amplitude
  each TR, and each step fills one line of k-space.
- **Frequency encoding (readout):** a frequency-encode/readout gradient is on *during* the echo (commonly
  along A-P) so that signal frequency encodes position along that axis; the echo is digitised across the
  readout.
- **k-space:** a raw data matrix of spatial frequencies. Each phase-encode step fills one line; central
  lines carry contrast and low spatial frequency (bulk signal), peripheral lines carry edge/detail (high
  spatial frequency). k-space is not the image.
- **Fourier transform:** a 2D Fourier transform converts the filled k-space into the final image,
  mapping spatial frequencies to pixel intensities.
- **Image-formation pipeline:** excite the chosen slice (RF + slice-select gradient), spatially encode
  (phase then frequency), sample the echo into k-space, repeat per TR until k-space is full, then Fourier
  transform to reconstruct.
- **Sequence placement (mechanism-level, not weighting):** gradient echo uses a gradient reversal to form
  its echo (no 180, so it decays with T2\* and typically uses a flip angle under 90); spin echo uses a
  180 refocusing pulse to form its echo; inversion recovery adds a preparatory 180 inversion before the
  excitation to control which tissue is nulled (STIR, FLAIR). Each still runs through the same encode /
  sample / reconstruct pipeline.

## Content to add

1. **Lesson 1 — "Spatial encoding: slice, phase, and frequency gradients into k-space"** —
   `{topic:"data-acquisition", kind:"education"}`, all six body fields. The three gradients and what each
   does (slice-select during RF; phase-encode stepped per TR; frequency-encode during readout); how
   phase-encode steps fill k-space line by line; center vs periphery of k-space (contrast vs detail); the
   Fourier transform reconstructs the image. exam_traps: the slice-select gradient is on during the RF
   pulse, the readout gradient is on during the echo; k-space center holds contrast/low spatial frequency
   and the periphery holds fine detail; k-space is raw data, not the image.
2. **Lesson 2 — "The image-formation pipeline: excite, encode, sample, reconstruct"** —
   `{topic:"pulse-sequences", kind:"education"}`, all six body fields. The end-to-end workflow (excite the
   slice, phase then frequency encode, sample the echo into k-space, repeat per TR, Fourier transform);
   how gradient echo (gradient-reversal echo, no 180), spin echo (180 refocus), and inversion recovery
   (preparatory 180 inversion to null a tissue) each form their signal and fit the same pipeline.
   exam_traps: gradient echo forms its echo by gradient reversal (no refocusing pulse); inversion recovery
   adds a 180 inversion BEFORE the excitation, not the refocusing 180 of spin echo; every 2D sequence
   still fills k-space one phase-encode line per TR before reconstruction.
3. **~16 quiz items** split 8 `data-acquisition` (which gradient is on during the RF pulse; which during
   the echo; what the phase-encode gradient does and that it steps per TR; each phase step = one k-space
   line; k-space center = contrast, periphery = detail; k-space is not the image; the Fourier transform
   reconstructs; slice thickness set by RF bandwidth and gradient) + 8 `pulse-sequences` (order of the
   pipeline steps; gradient echo forms its echo by gradient reversal; spin echo by a 180 refocus;
   inversion recovery adds a preparatory 180 inversion; where nulling fits; one phase line per TR; what
   the readout samples; reconstruction step). Four balanced-length options, no em dashes, no AI tells.
   No prompt may duplicate an existing bank question.

Voice per [[feedback_no_ai_tells_content]].

## Integration, testing, edge cases

Same pipeline as phases 2-5: Fable author writes `{lessons:[2], quiz:[~16]}` -> Fable accuracy review
(physics-correct, distinct from existing phase 4/5 content, plausible distractors, balanced lengths, no
dashes) -> controller appends to `data/course_content.json` (fresh ords after global max, byte-stable
`quiz_length_tools.dump`) -> bump `tests/test_course_depth.py` count 36 -> 38 -> guard + depth + images
tests green + `ruff check src/ tests/` -> idempotent MCP reseed by `body->>'title'`/`prompt`. No JS/engine
change. Branch off fresh main after #400 (phase-5 basic physics) merges so the baseline is 455 items /
depth 36. Edge cases: answer-length tell (guard), duplicate prompt/title (applier + reseed not-exists
guard), overlap with existing phase 4/5 content (accuracy reviewer + author instruction), depth-count
drift (bump the two `36`s to `38`).

## Out of scope

- Any `course.js` / curriculum-map change (both topics already mapped).
- Image-based questions (text only here).
- Re-teaching the TR/TE/TI weighting table (phase 4) or the T2\* refocusing detail (phase 5).
- k-space sampling parameters already covered in phase 4 (matrix, FOV, NEX, partial Fourier, parallel
  imaging).
- This is the final PDF phase; the PDF program is complete after it, and work pivots to class-owner
  sub-project B per [[project_owner_abilities]].
