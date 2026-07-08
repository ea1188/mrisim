# Course content: Neurovascular clinical protocols (PDF phase 2, region 3) — Design

**Goal:** Add neurovascular MRI content to the paid course — two reading lessons plus ~18 quiz items —
generalized from the "MR Intern Competency" deck's neurovascular section (brain MRA, brain MRV, neck
MRA), deepening the course's ARRT Procedures/angiography coverage.

**Status:** Approved 2026-07-08. Third region of PDF phase 2 (clinical protocols by region), following
Neuro (#393) and Spine (#394). See [[project_pdf_content_phases]].

## Context

Content lives in `data/course_content.json` (source; seeded to Supabase `course_content`, served by
`web/course.js`). Unlike Neuro/Spine (which split across `procedures-anatomy` and `procedures-protocols`),
this region is entirely **angiography**, so both lessons and all quiz go to a single existing,
already-mapped topic:

- `procedures-vascular` — Module 8 "Flow, function & artifacts" (MR angiography and venography: TOF, PC
  and contrast methods). Currently underweight at 1 education + 6 quiz. No `course.js` change needed
  (topic already in `TOPIC_CFG`, module 8 `premium: ["flow-artifacts", "procedures-vascular"]`).

Item shape `{topic, kind, ord, body}`; education `body` = `{title, html, keypoints, worked_example,
memory_hooks, exam_traps}`; quiz `body` = `{prompt, options[4], answer (0-idx), explain}`. Answer-length
guard forbids a keyed answer exceeding every distractor by >20%. All quiz keyed to index 0.

## Source & generalization

Source: `pdf education/MR Intern Competency 2025.pdf`, neurovascular section (pages 67-88). Generalize:
vendor sequence names → generic ("gradient echo (GRE)" not "Flash"; "a fast 3D T1 gradient echo (VIBE or
LAVA type)"; keep "time-of-flight (TOF)", "phase contrast (PC)", "MIP", "Circle of Willis" as generic);
the site-specific bolus-timing formula → the generic concept (test bolus / bolus tracking timed to the
arterial phase); no brands/sites/phone numbers.

Kept as generally true (ACR-consistent): brain MRA is usually non-contrast TOF, bright because inflowing
unsaturated blood enters a slab of saturated stationary tissue; coverage ~top of corpus callosum to skull
base; keep TOF isotropic; extend coverage by adding SLABS not slices-per-slab (too many slices per slab
causes the Venetian blind artifact at slab boundaries); reconstruct rotating Circle-of-Willis and carotid
MIPs; aneurysm best on TOF MRA while AVM/cavernoma are better on SWI/diffusion. Brain MRV evaluates dural
venous sinus thrombosis / central sinus obstruction, coverage top of skull to below foramen magnum,
non-contrast venogram = straight sag + straight cor 2D TOF, contrast venogram = axial 3D T1 GRE on the
AC-PC line with matched pre/post for MIP subtraction. Neck MRA indications stroke/CVA, carotid
stenosis/occlusion, dissection; non-contrast TOF can cover just around the bifurcation while a full study
covers skull base to aortic arch; contrast neck MRA uses a thin (~1.5 mm) coronal 3D GRE, weight-based
gadolinium, timed to the arterial bolus to beat venous contamination. Saturation-band direction sets the
vessel shown: a superior band ("sat up") displays arterial flow, an inferior band ("sat down") displays
venous flow; this demonstrates subclavian steal (reversed vertebral flow from a compromised subclavian).
Carotid dissection is best on a pre-contrast fat-sat T1 covering carotids and the arch, with the classic
bright crescent of intramural hematoma in the wall of an otherwise dark flowing vessel.

## Content to add

1. **Lesson 1 — "Brain MRA and MRV: time-of-flight, coverage, and reconstructions"** —
   `{topic:"procedures-vascular", kind:"education"}`, all six body fields. TOF principle, coverage,
   slab-vs-slices/Venetian-blind, isotropy, COW/carotid MIPs, aneurysm-vs-AVM sequence choice, and MRV
   (sinus thrombosis, coverage, matched pre/post subtraction). exam_traps: add slabs not slices per slab;
   TOF is bright from unsaturated inflow, not contrast.
2. **Lesson 2 — "Neck MRA and carotid technique: contrast timing, saturation bands, and dissection"** —
   `{topic:"procedures-vascular", kind:"education"}`, all six body fields. Neck MRA indications/coverage,
   weight-based contrast timed to the arterial bolus, sat-up/sat-down arterial-vs-venous, subclavian
   steal, and carotid dissection (pre-contrast fat-sat T1, bright intramural crescent). exam_traps:
   sat-up = arterial / sat-down = venous; dissection crescent on fat-sat T1 before contrast.
3. **~18 quiz items** (all `procedures-vascular`), ~9 brain MRA/MRV (TOF unsaturated-inflow; coverage
   corpus-callosum-to-skull-base; add slabs not slices/slab; keep TOF isotropic; aneurysm on TOF;
   AVM/cavernoma on SWI; COW/carotid MIP recons; MRV = dural sinus thrombosis; matched pre/post for
   contrast MRV subtraction) and ~9 neck/carotid (indications; skull-base-to-arch coverage; weight-based
   contrast timed to arterial bolus; sat-up = arterial; sat-down = venous; subclavian steal; dissection
   on pre-contrast fat-sat T1; bright intramural-hematoma crescent; add slabs not slices/slab). Four
   balanced-length options, no em dashes, no AI tells.

Voice per [[feedback_no_ai_tells_content]].

## Integration, testing, edge cases

Same pipeline as prior regions: Fable author writes `{lessons:[2], quiz:[~18]}` → Fable accuracy review
(ACR-consistent, fully generalized, plausible distractors, balanced lengths, no dashes) → controller
appends to `data/course_content.json` (fresh ords after global max, byte-stable `quiz_length_tools.dump`)
→ bump `tests/test_course_depth.py` count 21 → 23 → guard + depth + images tests green + `ruff check src/
tests/` → idempotent MCP reseed by `body->>'title'`/`prompt`. No JS/engine change. Edge cases:
answer-length tell (guard), duplicate prompt/title (applier + reseed not-exists guard), generalization
miss (accuracy reviewer), depth-count drift (bump the two `21`s to `23`).

## Out of scope

- The remaining phase-2 regions (MSK, Body) — future sub-projects.
- Any `course.js` / curriculum-map change (topic already mapped).
- Image-based questions (text only here).
