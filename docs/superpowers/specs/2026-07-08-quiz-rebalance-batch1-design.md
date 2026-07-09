# Premium Quiz Rebalance — Batch 1 Design

**Date:** 2026-07-08
**Status:** Approved (design), ready for implementation plan

## Goal

Grow the premium quiz pool toward the ARRT exam weighting the blueprint feature
(shipped #406) made concrete. Batch 1 targets the thinnest topics in Image
Production, the exam's largest and most under-built content category. Every new
question is anchored to a specific ARRT content-outline subtopic so it is
defensibly on-blueprint, not filler.

## Why these topics (audited mapping)

The premium pool (415 quiz items, 15 topics) rolls up to the 4 ARRT categories.
Mapping audited against where ARRT files each topic in its content outline
(`contrast-agents` is Patient Care / Pharmacology, not Image Production):

| ARRT category | Premium Q | % | Exam target |
|---|---|---|---|
| Image Production | 189 | 46% | 53% |
| Procedures | 153 | 37% | 28.5% |
| Patient Care | 44 | 11% | 8% |
| Safety | 29 | 7% | 10.5% |

Anchoring Procedures at 153 (= 28.5%) sets the target pool at ~537: Image
Production needs +96 and Safety +27; Patient Care is already at/over target.
This is a phased effort. Batch 1 takes the thinnest Image Production topics;
Safety and further Image Production growth are Batch 2+.

## Scope — Batch 1

Three Image Production topics, each grown to a floor of 16 (except flow-artifacts,
already 21, grown to 28):

| Topic | Now | Target | New Q |
|---|---|---|---|
| `three-d-recon` | 8 | 16 | +8 |
| `fat-suppression` | 10 | 16 | +6 |
| `flow-artifacts` | 21 | 28 | +7 |
| **Total** | | | **+21** |

Out of scope for Batch 1: Safety (+27), the larger Image Production topics
(image-quality 25, and the 27-34 range), Procedures (over target, do not grow),
Patient Care (at target).

## ARRT outline anchors (authoring source)

Each new question targets a named subtopic from the ARRT MRI content outline, and
must not duplicate an existing question in that topic (review the current items
first). Draw from:

**three-d-recon** (Image Production: 2D/3D imaging options, data manipulation,
postprocessing)
- 2D multislice vs 3D volumetric acquisition; slab excitation and partitions
- isotropic voxels and free reformatting
- MIP reformation, MPR, subtraction
- SNR and scan-time tradeoffs of 3D vs 2D
- slice-direction aliasing (slab wrap) and how it is controlled
- 3D GRE / SSFP volumetric sequences
- contiguous partitions vs slice gap

**fat-suppression** (Image Production: imaging options, suppression techniques)
- STIR (short-TI inversion recovery): TI null of fat, why it is avoided after
  gadolinium
- chemical (spectral, frequency-selective) fat saturation
- Dixon method: in-phase / out-of-phase, water-fat separation
- field-strength dependence (chemical shift, B0 homogeneity sensitivity)
- in-phase / out-of-phase TE selection at 1.5T vs 3T
- STIR vs spectral-sat tradeoffs (B0 sensitivity, post-contrast use)
- water suppression

**flow-artifacts** (Image Production: artifacts — motion and flow; imaging options)
- ghosting along the phase-encode axis from pulsatile flow
- spatial saturation (pre-sat) bands to suppress inflowing signal
- gradient moment nulling / flow compensation
- flow-related enhancement (inflow) vs high-velocity signal loss / dephasing
- even-echo rephasing
- swapping phase and frequency to reposition ghosts
- cardiac / peripheral gating for pulsatile artifact

## Data model and item shape

New items append to `data/course_content.json` (the source; the course serves live
from the Supabase `course_content` table). Each item:

```json
{
  "topic": "<three-d-recon | fat-suppression | flow-artifacts>",
  "kind": "quiz",
  "ord": <fresh, in a new block 1140+>,
  "body": {
    "prompt": "...",
    "options": ["<correct>", "<distractor>", "<distractor>", "<distractor>"],
    "answer": 0,
    "explain": "..."
  }
}
```

Convention (matches existing items): author the correct option at index 0 with
`answer: 0`; `course.js` shuffles option order at render, and the answer-length
guard reads the keyed index, not position 0. Use a fresh contiguous ord block
starting at 1140 (max ord currently in use is 1131) so new items are easy to
identify and reseed.

## Authoring and accuracy (the credibility core)

- Registry difficulty; four options; exactly one correct.
- No AI-tell punctuation, no em dashes; natural clinical prose.
- Every question passes the answer-length guard: the keyed answer must not exceed
  1.2x the length of every distractor (`scripts/quiz_length_tools.py`
  `flagged_items`), so the correct answer is not guessable by length.
- Distractors must be plausible and specifically wrong (a real misconception),
  not obviously absurd.
- Explanations state why the key is right and, where useful, why a distractor is
  wrong.
- **User approval gate:** the drafted batch is presented for review before
  seeding. The user (an MR technologist) verifies physics and clinical accuracy.
  Nothing reaches Supabase until approved.

## Seed pipeline

1. Append the approved items to `data/course_content.json` via
   `scripts/quiz_length_tools.py` `load()` / `dump()` (byte-stable: indent 2,
   `ensure_ascii=False`, trailing newline).
2. Reseed the Supabase `course_content` table (course `mri-core`) so the live
   course serves the new questions. Committing alone does not ship them.

## Testing

- `tests/test_quiz_length.py`: the full pool has no newly flagged items (the 21
  new questions all pass the answer-length guard).
- `tests/test_course_depth.py`: existing depth guard still passes.
- A count assertion: `three-d-recon` >= 16, `fat-suppression` >= 16,
  `flow-artifacts` >= 28 quiz items in `data/course_content.json`.

## Global constraints

- Content accuracy is paramount (paid registry-prep product). Every question
  anchored to a named ARRT outline subtopic; user approves before seeding.
- No AI-tell punctuation / em dashes; natural prose.
- Answer-length guard must stay green (no new flagged items).
- Reseed Supabase after the content edit; a commit alone does not ship.
- No `Co-Authored-By: Claude` trailers on commits.
- Run `ruff check src/ tests/` and the web test suite before merge.

## Out of scope

- Safety and larger Image Production topics (Batch 2+).
- Procedures and Patient Care (at or over target).
- Pointing the readiness panel at the premium pool (it reads the free pool; a
  separate follow-up).
- The free 100-question pool.
