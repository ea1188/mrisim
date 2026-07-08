# Course content: MSK clinical protocols (PDF phase 2, region 4) — Design

**Goal:** Add musculoskeletal MRI content to the paid course — two reading lessons plus ~20 quiz items —
generalized from the "MR Intern Competency" deck's MSK section (shoulder, knee, hip, wrist, foot/ankle,
fat-suppression, metal reduction, arthrograms), deepening the course's ARRT Procedures coverage.

**Status:** Approved 2026-07-08. Fourth region of PDF phase 2 (largest cluster), following Neuro (#393),
Spine (#394), Neurovascular (#395). See [[project_pdf_content_phases]].

## Context

Content lives in `data/course_content.json` (source; seeded to Supabase `course_content`, served by
`web/course.js`). Same two existing, already-mapped topics as Neuro/Spine, so no `course.js` change:

- `procedures-anatomy` — Module 4 (regional anatomy: planes and sequences by body part). After
  Neuro+Spine: 3 education + 29 quiz.
- `procedures-protocols` — Module 9 (building a protocol). After Neuro+Spine: 3 education + 32 quiz.

Item shape `{topic, kind, ord, body}`; education `body` = `{title, html, keypoints, worked_example,
memory_hooks, exam_traps}`; quiz `body` = `{prompt, options[4], answer (0-idx), explain}`. Answer-length
guard forbids a keyed answer exceeding every distractor by >20%. All quiz keyed to index 0. MSK is the
largest region, so the quiz set is ~20 (10/10) rather than ~18.

## Source & generalization

Source: `pdf education/MR Intern Competency 2025.pdf`, MSK section (pages 88-115). Generalize: site
abbreviations ("LOC") removed; vendor names generalized (the metal-artifact sequence becomes "a dedicated
metal-artifact-reduction sequence (a SEMAC or MAVRIC type)"; "3D radial" not "Swiss radials"; Dixon and
SEMAC/MAVRIC allowed as generic MSK technique terms); no phone numbers or site names. "1.5T" kept
(susceptibility artifact is genuinely smaller at lower field).

Kept as generally true (ACR-consistent): shoulder positioned arm-at-side palm-up (external rotation) with
a sandbag for a cleaner labral profile clear of the bicipital groove, coverage SC joint to below glenoid,
coronal perpendicular / sagittal parallel to the glenohumeral joint, rotator cuff = SITS (supraspinatus,
infraspinatus, teres minor, subscapularis); knee laser at the inferior patella (apex), coverage
quadriceps attachment to patellar tendon/fat pad; hip phased-array coil top at iliac crest, feet tied
(toes in, heels apart) for internal rotation, axial coverage above the joint to below the lesser
trochanter; wrist superman position, cover all carpal bones; foot/ankle coil feet-first, protocols
forefoot-midfoot / ankle-hindfoot / whole foot, indications include Morton neuroma, Lisfranc, Achilles;
STIR replaces fat-sat T2 when metal is near or fat suppression is inhomogeneous (spectral fat-sat fails in
a distorted field); metal escalation (small screw = routine metal reduction, often at 1.5T; joint
replacement = a dedicated metal-artifact-reduction sequence); in/out-of-phase added for a bone-tumor
question; MR arthrogram is a two-part procedure with contrast injected directly into the joint
(intra-articular) then imaged, done on shoulder/elbow/wrist/hip/knee/ankle to show cartilage, labral, and
ligament tears.

## Content to add

1. **Lesson 1 — "MSK MRI protocols: shoulder, knee, hip, wrist, and foot"** —
   `{topic:"procedures-anatomy", kind:"education"}`, all six body fields. Per-joint coil, positioning,
   coverage, and landmarks. exam_traps: knee laser at the inferior patella (apex) not the joint center;
   rotator cuff = supraspinatus, infraspinatus, teres minor, subscapularis.
2. **Lesson 2 — "MSK technique: fat suppression, metal reduction, and arthrograms"** —
   `{topic:"procedures-protocols", kind:"education"}`, all six body fields. STIR-vs-fat-sat-T2 decision,
   metal-reduction escalation, in/out-of-phase for tumor, and the intra-articular arthrogram. exam_traps:
   switch to STIR with metal or inhomogeneous fat-sat; the arthrogram injects into the joint, not a vein.
3. **~20 quiz items** split ~10 `procedures-anatomy` (rotator cuff indications; palm-up shoulder
   positioning; shoulder coverage; SITS muscles; knee laser at patella apex; knee indications; hip coil at
   iliac crest + feet tied; hip coverage; wrist superman + carpal coverage; foot/ankle coil + Morton or
   Lisfranc) and ~10 `procedures-protocols` (fat-sat T2 to STIR with metal; STIR for inhomogeneous fat-sat;
   small screw = routine metal reduction; joint replacement = dedicated metal-artifact sequence; metal
   reduction at 1.5T; in/out-of-phase for bone tumor; arthrogram is intra-articular; arthrogram is two-part
   inject-then-image; arthrograms show labral/TFCC/cartilage tears; shoulder coronal perpendicular to the
   glenohumeral joint). Four balanced-length options, no em dashes, no AI tells.

Voice per [[feedback_no_ai_tells_content]].

## Integration, testing, edge cases

Same pipeline as prior regions: Fable author writes `{lessons:[2], quiz:[~20]}` → Fable accuracy review
(ACR-consistent, fully generalized, plausible distractors, balanced lengths, no dashes) → controller
appends to `data/course_content.json` (fresh ords after global max, byte-stable `quiz_length_tools.dump`)
→ bump `tests/test_course_depth.py` count 23 → 25 → guard + depth + images tests green + `ruff check src/
tests/` → idempotent MCP reseed by `body->>'title'`/`prompt`. No JS/engine change. Edge cases:
answer-length tell (guard), duplicate prompt/title (applier + reseed not-exists guard), generalization
miss (accuracy reviewer), depth-count drift (bump the two `23`s to `25`).

## Out of scope

- The final phase-2 region (Body) — future sub-project.
- Any `course.js` / curriculum-map change (both topics already mapped).
- Image-based questions (text only here).
