# ARRT Blueprint Alignment — Design

**Date:** 2026-07-08
**Status:** Approved (design), ready for implementation plan

## Goal

Show the student their registry readiness mapped to the real ARRT MRI content
categories, weighted the way the actual exam is weighted, so their next study
session targets what the exam actually tests. The differentiator over a generic
quiz score is a single weighted headline number plus an auditable per-category
breakdown that mirrors the official ARRT MRI Content Specifications.

## Source of truth (verified)

ARRT MRI Content Specifications, ARRT Board Approved January 2024, implementation
date February 1, 2025 (the current spec). 200 scored questions (plus 30 unscored
pilot).

| Content category | Scored Q | Weight | Subcategories (Q) |
|---|---|---|---|
| Patient Care | 16 | 0.080 | Patient Interactions & Management (16) |
| Safety | 21 | 0.105 | MRI Screening & Safety (21) |
| Image Production | 106 | 0.530 | Physical Principles (40), Sequence Parameters & Options (36), Data Acquisition/Processing/Storage (30) |
| Procedures | 57 | 0.285 | Neurological (25), Body (15), Musculoskeletal (17) |
| **Total** | **200** | **1.000** | |

Weights are `scored / 200`, carried to three decimals: 0.080, 0.105, 0.530, 0.285.

Source PDF: ARRT MRI Content Specifications 2025 (Board Approved Jan 2024).

## Mapping (internal quiz categories → ARRT categories)

The course has 8 quiz categories. Each maps to exactly one ARRT category. The
mapping is auditable — every row follows where ARRT itself files the topic in its
content outline.

| Quiz category | ARRT category | Rationale |
|---|---|---|
| `patient-care` | Patient Care | direct |
| `safety` | Safety | direct (MRI Screening & Safety) |
| `sequences` | Image Production | SE/GRE/IR/EPI/DWI live under Data Acquisition then Pulse Sequences |
| `image-quality` | Image Production | SNR/CNR/resolution/TR-TE effects under Sequence Parameters & Options plus QC |
| `artifacts` | Image Production | ARRT lists artifacts under Physical Principles then Artifacts |
| `perfusion` | Image Production | ARRT files the technique under Data Acquisition then Pulse Sequences then perfusion |
| `pathology` | Procedures | Procedures focus-of-questions is "pathological considerations" |
| `anatomy` | Procedures | Procedures focus-of-questions is "Anatomy and Physiology" |

Rollup:
- Patient Care: `patient-care`
- Safety: `safety`
- Image Production: `sequences`, `image-quality`, `artifacts`, `perfusion`
- Procedures: `pathology`, `anatomy`

### Procedures honesty note

ARRT Procedures also tests positioning, coil selection, landmarking, protocol,
gating, and contrast effect region-by-region (Neurological, Body, MSK). The
course teaches much of that in the Protocol Planning positioning trainer and in
lessons, not in a quiz category that yields an accuracy signal. Therefore
Procedures readiness is computed from the pathology plus anatomy accuracy we can
measure, and the Procedures row carries a visible label:

> Covers pathology and anatomy. Positioning, coils, and protocol are practiced in
> Protocol Planning.

Folding the positioning trainer in as a Procedures signal, or adding a
Procedures-oriented quiz slice (positioning/coils/protocol), are roadmap items,
not part of this work.

## Readiness signal

Computed from quiz accuracy, weighted. Source data is `mrisim_quiz_progress_v1`
in `localStorage`, written by the standalone quiz (`web/quiz.js`), shape:

```js
{ "<categoryId>": { best: <max score>, total: <pool size in that run>, runs: <count> } }
```

`accuracy = best / total` per category; a category is "attempted" when it has an
entry with `total > 0`.

### Per ARRT category

For an ARRT category with member quiz categories `M`:
- `attempted` = members of `M` with a progress entry (`total > 0`).
- `right = sum of best` over attempted members; `asked = sum of total` over attempted members.
- `accuracy = asked > 0 ? right / asked : null` (null means "Not started", never 0).
- `coverage = attempted.length / M.length` (fraction of member categories practiced).

### Overall

- `projected = sum of (accuracyOrZero * weight)` over all 4 categories, where an
  unattempted category contributes 0. This is the single "if the exam were today"
  number. It rises as the student both practices more and scores higher, and it
  cannot be inflated by grinding a low-weight category.
- `coverage = sum of (categoryCoverage * weight)` over all 4 categories — the
  share of the weighted blueprint the student has faced at all. Explains the
  projected ceiling.

Both are in [0, 1]; render as whole-number percents.

## Components

1. **`web/blueprint.js`** — pure UMD module (browser: `window.Blueprint`; node:
   `module.exports`). Exports `ARRT_BLUEPRINT` (the verified constant) and
   `readiness(progress)`. No DOM, no I/O — fully unit-testable.
2. **`web/course.js`** — `renderReadiness()` reads `localStorage`
   (`mrisim_quiz_progress_v1`), calls `Blueprint.readiness`, builds the panel DOM,
   and injects it into the course page. No physics/scoring logic here — it only
   renders what `blueprint.js` computes.
3. **`web/course.html`** — `<script>` tag for `blueprint.js`, the panel container,
   and CSS.
4. **`web/blueprint.test.mjs`** — node --test, joins the existing web suite.

## UI

A "Registry readiness" panel on the course page (`course.html`, the study hub).

- **Headline:** projected readiness percent plus a coverage meter ("You've
  practiced N% of the weighted blueprint").
- **Four category rows**, ordered by exam weight (Image Production 53% first), each
  with: category name, an exam-weight chip ("53% of exam"), an accuracy bar (or
  "Not started"), and coverage. The weight ordering makes the visual hierarchy
  itself teach where the exam's mass sits.
- **Procedures row** carries the honesty label above.

Aesthetic: clinical/professional per the site design system — flat solid accent
bars (no gradients), 2px corners, tabular numerals, no emoji. Copy uses natural
prose with no em dashes or AI-tell punctuation.

## Data flow

```
quiz.html run -> saveBest() -> localStorage mrisim_quiz_progress_v1
course.html load -> renderReadiness() -> read that key -> Blueprint.readiness() -> DOM
```

No network calls. Readiness reflects whatever quiz progress is present locally.

## Testing

`web/blueprint.test.mjs`:
- Blueprint integrity: `scored` values sum to 200; `weight` values sum to 1.0
  (within float tolerance); the 8 quiz category ids appear across `members`
  exactly once total (no dup, no omission).
- `readiness` math:
  - empty progress -> every category `accuracy: null`, `coverage: 0`; overall
    `projected: 0`, `coverage: 0`.
  - full progress (all 8 categories, known bests) -> per-category accuracy and the
    weighted `projected` match hand-computed values.
  - partial (only some members of a category attempted) -> `accuracy` uses only
    attempted members; `coverage` is the attempted fraction.
  - unattempted category -> contributes 0 to `projected`, `null` accuracy (not a 0%
    that reads as "failed").
  - thin sample (best 3/3 in one member) -> accuracy 1.0 but coverage < 1, so the
    row is visibly low-confidence.

## Global constraints

- No backend: pure client-side from `localStorage`. No Supabase migration, no
  reseed.
- Content/UI copy: no em dashes or AI-tell punctuation; clinical aesthetic (no
  emoji, no gradients, 2px corners, flat solid accents).
- Blueprint numbers are verbatim from the verified ARRT spec: 16 / 21 / 106 / 57,
  weights 0.080 / 0.105 / 0.530 / 0.285.
- No `Co-Authored-By: Claude` trailers on commits.
- Run ruff on `src/` and `tests/` (no Python changes expected, but the CI gate
  runs) and the web test suite before merge.

## Known limitation (out of scope)

`mrisim_quiz_progress_v1` is not in the cross-device progress sync set
(`course_logic.js` `mergeProgress` handles `mrisim_course_*` keys). Readiness
therefore reflects local progress only. Folding quiz progress into sync is a
clean future follow-up.

## Out of scope

- Cross-device sync of quiz progress.
- Diagnostic/mastery as readiness signals (quiz accuracy only, per approval).
- Procedures positioning/coil/protocol assessment (roadmap).
- Owner/instructor-facing view (this is the student view).
