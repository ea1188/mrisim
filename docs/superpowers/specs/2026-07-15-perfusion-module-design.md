# Perfusion advanced-imaging module — design

Date: 2026-07-15
Status: approved (build), authoring

## Goal

Add the first advanced-imaging module to the guided course: **Perfusion** (DSC, DCE, ASL).
New curriculum module + exclusive education content in Supabase `course_content` + premium
quiz items + two diagrams. First of a planned advanced-imaging track.

## Placement decision

- **New curriculum module** `"11 · Perfusion & advanced imaging"` in `data/lessons.json` (and
  `web/lessons.json` generated copy), education-only (`lessons: []`).
- Reuse the existing **`perfusion`** topic (already an ARRT-blueprint member and a declared but
  empty quiz topic) for both the education cards and the quiz items.
- `web/course.js` `TOPIC_CFG`: add `"11 · Perfusion & advanced imaging": { premium: ["perfusion"], quiz: ["perfusion"] }`, and REMOVE `perfusion` from module 8's quiz list (`"8 · Flow, function & artifacts"`: `quiz: ["artifacts", "perfusion"]` → `["artifacts"]`) so it isn't shown twice.
- `web/blueprint.js` `PREMIUM_MAP`: add `"perfusion": "image-production"` (matches the ARRT_BLUEPRINT membership) — required or the blueprint guard test fails once perfusion quiz items exist.

## Content (authored in `data/course_content.json`, then seeded to prod)

Education cards (topic `perfusion`, kind `education`, ord 1326+), house schema
`{title, html, keypoints[], worked_example, memory_hooks[], exam_traps[]}`, same voice as
existing cards (concise exam-oriented prose, US spelling, **no em dashes / AI tells**):

1. **Dynamic susceptibility contrast (DSC): first-pass bolus tracking** — gadolinium bolus,
   T2\*-weighted EPI, the transient signal drop as contrast passes, CBV/CBF/MTT maps,
   the concentration-time curve, recirculation, why a fast injection + tight timing matter.
2. **Dynamic contrast enhancement (DCE): permeability and Ktrans** — T1-weighted repeated
   acquisition, uptake/washout curves, Ktrans/ve, tumor grading and treatment response,
   contrast with DSC (T1 vs T2\*, permeability vs bolus).
3. **Arterial spin labeling (ASL): perfusion without contrast** — magnetically labeling
   inflowing arterial blood, label vs control subtraction, PASL/pCASL, post-label delay,
   low SNR and averaging, when it is preferred (no gadolinium, serial studies, renal
   impairment, pediatrics).
4. **Choosing a perfusion method** — DSC vs DCE vs ASL trade-offs, contrast vs non-contrast,
   what each measures, common clinical uses (stroke, tumor, dementia).

Quiz (topic `perfusion`, kind `quiz`, ord follows), ~10 items, schema
`{prompt, options[4], answer, explain}`, ARRT-registry style, each testing a distinct fact
(DSC uses T2\*, ASL needs no contrast, Ktrans meaning, PLD, etc.). Every item render-and-verify
bar for text facts (no image questions here).

## Diagrams (reuse the engine — added AFTER batch 4 #444 merges)

- **DSC signal-time curve** → a new education card title, `DIAGRAM_MAP` key. Signal drops
  during first pass (T2\* effect) then recovers; marker for peak drop. Reuses `makePlot`.
- **ASL label - control** → schematic of label and control images and their subtraction
  (small canvas or SVG). Reuses the canvas/SVG primitives.
- These go in a follow-up once `course_diagrams.js` on main includes batch 4.

## Production seed (needs owner confirmation, per prod-DB rule)

- Author into `data/course_content.json` (source of record), then INSERT the new education +
  quiz rows into Supabase `public.course_content` (course `mri-core`) via a reviewed SQL batch,
  same mechanism as the spine content fix. Verify counts after.

## Verification
- `npm run test:web` (blueprint guard: perfusion now in PREMIUM_MAP; guard that DIAGRAM_MAP
  keys are education titles once diagrams land), `npm run lint`, `ruff check src/ tests/`.
- Course renders module 11 with the four education cards + the perfusion quiz; readiness
  attributes perfusion to image-production.
- Branch → PR → gate-merge (source). Prod seed run separately with confirmation.

## Out of scope (YAGNI)
- The other advanced modules (diffusion-deep, cardiac, MRA-advanced, MRS, fMRI, mapping) -
  each its own later project.
