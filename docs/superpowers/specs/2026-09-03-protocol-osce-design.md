# Protocol OSCE — design spec

**Date:** 2026-09-03 · **Status:** awaiting owner review
**Owner decisions locked:** retryable formative mode (not a locked exam); instructor sync included in v1.
**Quality bar (owner):** very high standard — no hand-tuned targets, fully tested rubric, educational feedback, independent content QC before learners see it.

## Concept

Graded clinical scenarios inside the protocol planner. A learner gets a clinical stem
("45-year-old with left L5 radiculopathy — plan the lumbar spine MRI"), builds the exam
with the planner's normal workflow (sequences, parameters, orientation, angulation,
coverage), and submits. A rubric grades the submitted protocol per criterion with
educational feedback and a score. Retry is always available; each attempt logs a
formative activity the instructor Insight page can see.

Everything graded already exists in planner state — `{orientation, slice, tilt, rot,
inplane_off, fov_pct}` per series plus `params` and the sequence queue. Nothing new is
instrumented; the OSCE is a grader over the workspace, not a new workspace.

## Grading model

A scenario is a list of **criteria**, each independently graded to full / partial / no
credit, each carrying authored feedback that explains the clinical *why* (not just
"wrong"). Criterion types:

1. **required_series** — the protocol contains a series matching a pattern:
   sequence family (or contrast weighting computed from params), orientation,
   fat-suppression state. Missing → 0 with feedback naming what's missing and why
   it's needed.
2. **angulation** — |applied tilt − derived target| within tolerance. Full credit
   band and partial band both derived from the anatomy (see Ground truth), with
   floors (±5° full / ±10° partial) so grading is never harsher than clinical practice.
   Only used where ground truth supports it (v1: the lumbar disc scenario).
3. **slice_targeting** — the slice position lands within the target structure's band
   (component centroid ± half-extent along the slice axis).
4. **coverage** — the slab (n_slices × thickness against FOV geometry) spans the
   required structure range (e.g., conus through S1).
5. **param_check** — scenario-specific parameter reasoning: STIR TI in the
   fat-nulling range, metal-reduction choices (higher BW / STIR over spectral fat-sat),
   DWI b-value, T2 TE floors. Each check names the physics reason in its feedback.

Score = Σ points, reported per criterion + overall %. No pass/fail gate in v1
(formative); the review screen orders criteria failed-first.

## Ground truth (verified against the shipped data, 2026-09-03)

`data/spider_spine/atlas.npy` (223×145×128): label 15 = intervertebral discs,
which separate into **exactly 7 connected components ≥1000 voxels** with clean
monotone centroids along axis 0 — T12-L1 through L5-S1. Disc identity = rank from
the caudal end. Vertebrae (19) and cord (21) give coverage ranges.

`scripts/derive_osce_targets.py` (offline, tested, never ships):
- loads the region atlas, extracts disc components (connected components of
  label 15, size-filtered, sorted along the spine axis);
- disc plane normal via PCA of the component's voxels (smallest principal axis);
- converts that normal into the planner's tilt convention by solving against the
  engine's own `oblique.plane_from_angles` — the same function that renders the
  band — so target and UI can never disagree by convention;
- emits slice bands and coverage ranges from component bounding boxes;
- merges authored scenario text (`data/osce_scenarios.json`, source of truth for
  stems/criteria/feedback) with derived numbers → `web/osce.json` (generated,
  committed, like lessons.json).

Tests: a synthetic label volume with a known plane angle must round-trip through the
derivation to within 1°; the spine derivation must find exactly 7 discs with
anatomically plausible angles (monotone lordotic progression); regenerating must be
byte-stable.

## Scenarios v1 (3)

1. **Lumbar radiculopathy** (spine region) — sag T1, sag T2, axial T2 angled to the
   L4-L5 disc. Grades: series set, axial angulation vs derived disc plane, slice
   targeting on the disc, sag coverage conus→S1.
2. **Knee internal derangement** — PD fat-sat in two planes + a T1; grades series
   set, fat-sat reasoning, coverage. No angulation grading (no reliable ground
   truth in the knee atlas — honesty over false precision).
3. **Brain, first seizure** — axial FLAIR + T2 + T1 + DWI; grades series set
   (FLAIR selection is the teaching point), DWI b-value, whole-brain coverage.

Content QC: before the UI PR merges, an independent Opus reviewer audits stems,
criteria, and feedback for clinical accuracy against the course's own teaching
material (same process as the course QC program).

## Architecture

- **`web/osce_rubric.js`** — pure UMD module (pattern: course_logic.js). API:
  `OsceRubric.grade(scenario, submission) → {criteria:[{id,label,verdict,points,max,feedback}], points, max, pct}`
  where `submission` = the planner queue's `{sequence, params, plan}` list.
  No DOM, no fetch. `web/osce_rubric.test.mjs` fixtures per scenario: the ideal
  protocol, plus common-error submissions (missing series, unangled axial, slice
  off target, coverage short, STIR TI wrong) each asserting the exact verdict set.
- **protocol.js UI** — OSCE entries join the exam selector; opening one shows the
  stem panel (design-system styling: flat, no emoji) and the normal planning
  workspace; a Submit-exam button grades the current queue and renders the
  per-criterion review; Retry re-enters planning with the same scenario and the
  queue intact. Keyboard/AA obligations inherited from the a11y program apply.
- **Instructor sync** — on submit: `Accounts.logActivity("osce", scenarioId, points, max)`.
  Migration 0017 bumps the activity-kinds CHECK constraint (known gotcha: unknown
  kinds are rejected SILENTLY — the 0014 lesson); Insight gains an OSCE column.

## Phasing (three PRs, each independently shippable)

- **A** — schema + derivation script + generated targets + rubric engine + full test
  suite (dormant: no UI). Gate: all tests, ruff/mypy on the script.
- **B** — planner UI + protocol_smoke extension driving one full OSCE headlessly
  (open scenario → plan → submit → assert criteria render). Gate: smoke + content QC
  pass complete.
- **C** — migration 0017 + logActivity + Insight column. Gate: migration applied to
  prod, activity visible end-to-end.

## Non-goals (v1)

Locked/timed exam mode; scenario authoring UI; more than 3 scenarios; partial-credit
tuning per criterion type beyond the two bands; contrast-administration simulation.
