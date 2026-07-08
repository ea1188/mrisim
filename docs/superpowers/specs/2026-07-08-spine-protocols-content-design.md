# Course content: Spine clinical protocols (PDF phase 2, region 2) — Design

**Goal:** Add spine clinical-protocol content to the paid course — two reading lessons plus ~18 quiz
items — generalized from the "MR Intern Competency" deck's spine section, deepening the course's ARRT
Procedures coverage (cervical, thoracic, lumbar, and total-spine plus technique).

**Status:** Approved 2026-07-08. Second region of PDF phase 2 (clinical protocols by region), following
Neuro (shipped #393). Same shape and pipeline as the Neuro region. See [[project_pdf_content_phases]].

## Context

Content lives in `data/course_content.json` (source; seeded to Supabase `course_content`, served by
`web/course.js`). Two existing, already-mapped topics are the homes, so no `course.js` change:

- `procedures-anatomy` — Module 4 "Reading pathology" (regional anatomy: planes and sequences by body
  part). After Neuro: 2 education + 20 quiz.
- `procedures-protocols` — Module 9 "Putting it together" (building a protocol). After Neuro: 2
  education + 23 quiz.

Item shape `{topic, kind, ord, body}`; education `body` = `{title, html, keypoints, worked_example,
memory_hooks, exam_traps}`; quiz `body` = `{prompt, options[4], answer (0-idx), explain}`. The
answer-length guard (`tests/test_quiz_length.py`) forbids a keyed answer exceeding every distractor by
>20%. All quiz keyed to index 0 (course.js shuffles at render).

## Source & generalization

Source: `pdf education/MR Intern Competency 2025.pdf`, spine section (pages 35-66). Generalize all
site/brand specifics: named sites (e.g. "Tisch") removed; vendor sequence trade names → generic
descriptors ("gradient echo (GRE)" not "Flash", "3D TSE (SPACE/CUBE type)", "STIR", "TSE", "CISS/FIESTA",
"in and out of phase"); no phone numbers or floor/site names; a "vitamin E capsule" stays as a generic
skin/table level-marker.

Kept as generally true (ACR-consistent): head/neck coil for cervical; sagittal coverage per level
(cervical pons/4th ventricle to ~T2-T3; thoracic ~C7 to L1; lumbar ~T12 to S2); the Sag T2 / Sag T1 /
Sag STIR core, with STIR best for MS, metastases, fracture, and infection; axial GRE shows nerve roots
and osteophytes but is avoided near metal (susceptibility blooming); anterior saturation band suppresses
swallowing/cardiac/breathing motion and reduces CSF pulsation; a vitamin E capsule marker helps count
vertebral levels on a thoracic study; odd slices per lumbar disc (center slice through the disc);
post-operative lumbar spine requires contrast to separate enhancing scar from non-enhancing recurrent
disc; total-spine assembly (two sagittal packages overlapping ~2 disc spaces at 3 mm, smallest FOV);
bone-vs-neuro routing (C/T/L BONE run separately, NEURO run as one total spine); drop metastases (from a
primary brain tumor, image the whole sac including the sacrum, often no pre-contrast axials) versus bony
metastases (lung/colon/breast, usually no contrast, in/out-of-phase can help); post-contrast fat-sat T1;
and the metal-reduction toolkit (TSE over GRE, higher bandwidth, higher turbo factor, thinner slices,
STIR over fat-sat T2, lower TE, higher resolution, swap phase-encode direction, more averages);
vertebral counts 7 cervical, 12 thoracic, 5 lumbar.

## Content to add

1. **Lesson 1 — "Spine MRI protocols: cervical, thoracic, and lumbar"** —
   `{topic:"procedures-anatomy", kind:"education"}`, all six body fields. Covers coil/coverage/sequences
   per level, the T2/T1/STIR core, sat bands, the vitamin E level marker, and the post-op lumbar contrast
   rule. exam_traps include "no GRE near hardware" and "post-op lumbar gets contrast (scar enhances,
   recurrent disc does not)".
2. **Lesson 2 — "Total spine and technique: bone versus neuro, drop metastases, and metal reduction"** —
   `{topic:"procedures-protocols", kind:"education"}`, all six body fields. Covers total-spine assembly,
   bone-vs-neuro routing, drop vs bony mets, post-contrast fat-sat T1, and the metal-reduction toolkit.
   exam_traps include the bone-vs-neuro routing and "STIR over fat-sat T2 / TSE over GRE near metal".
3. **~18 quiz items** split ~9 `procedures-anatomy` (cervical coil; cervical sag coverage; STIR best for
   MS/mets/fracture; axial GRE nerve roots but avoid near metal; anterior sat band; vitamin E level count;
   lumbar T12-S2 coverage; post-op lumbar contrast; herniation/syrinx on T2) and ~9 `procedures-protocols`
   (bone-separate vs neuro-total; two overlapping sag packages; smallest FOV; drop mets from brain tumor +
   image sacrum; bony mets no contrast; metal reduction raise bandwidth; STIR over fat-sat T2 near metal;
   TSE over GRE near metal; 7/12/5 vertebral counts). Four balanced-length options, no em dashes, no AI
   tells.

Voice per [[feedback_no_ai_tells_content]].

## Integration, testing, edge cases

Identical to the Neuro region: Fable author writes a patch `{lessons:[2], quiz:[~18]}` →
Fable accuracy review (ACR-consistent, fully generalized, plausible distractors, balanced lengths, no
dashes) → controller appends to `data/course_content.json` (fresh ords after global max, byte-stable
`quiz_length_tools.dump`) → bump `tests/test_course_depth.py` count 19 → 21 → guard + depth + images
tests green + `ruff check src/ tests/` → idempotent MCP reseed by `body->>'title'`/`prompt`. No JS/engine
change, so `npm run test:web` and the engine suite are unaffected. Edge cases: answer-length tell (guard),
duplicate prompt/title (applier + reseed not-exists guard), generalization miss (accuracy reviewer),
depth-count drift (bump the two `19`s to `21`).

## Out of scope

- The remaining phase-2 regions (Neurovascular, MSK, Body) — future sub-projects.
- Any `course.js` / curriculum-map change (both topics already mapped).
- Image-based questions (text only here).
