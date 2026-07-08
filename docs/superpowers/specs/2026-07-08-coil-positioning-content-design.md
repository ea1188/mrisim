# Course content: Coil selection & positioning (PDF phase 3) — Design

**Goal:** Add MRI coil and positioning content to the paid course — three reading lessons plus ~20 quiz
items — generalized from the "Coil and Positioning" staff deck (coil physics and types, per-region coil
selection and positioning, and RF-heating safety), deepening the course's instrumentation, procedures,
and safety coverage. This is **PDF phase 3**, following phase 1 (contrast reactions, #392) and phase 2
(clinical protocols by region, #393-#397).

**Status:** Approved 2026-07-08. Topic split ("all three topics", 3 lessons) chosen by the user. See
[[project_pdf_content_phases]].

## Context

Content lives in `data/course_content.json` (source; seeded to Supabase `course_content`, served by
`web/course.js`). Unlike phase 2 (regional protocols under `procedures-*`), this deck is instrumentation
plus safety, so it spans three existing, already-mapped topics. **No `course.js` change** (all three are
already in `TOPIC_CFG`):

- `instrumentation` — Module 1 "What an MRI image is" (coil physics and coil types).
- `procedures-anatomy` — Module 4 "Reading pathology" (per-region coil selection and positioning).
- `safety` — Module 10 "Safety & patient care" (RF heating: SAR, B1+rms, burns).

Item shape `{topic, kind, ord, body}`; education `body` = `{title, html, keypoints, worked_example,
memory_hooks, exam_traps}`; quiz `body` = `{prompt, options[4], answer (0-idx), explain}`. Answer-length
guard forbids a keyed answer exceeding every distractor by >20%. All quiz keyed to index 0 (course.js
shuffles at render, so not a tell). ~20 quiz split ~7 instrumentation / ~7 procedures-anatomy / ~6 safety.

## Source & generalization

Source: `pdf education/Coil and Positioning 2026.pdf` (42 pages). Generalize: named scanner/model tables
(Aera, Sola, Skyra, Vida, Prisma, Biograph mMR, GE Discovery) removed and replaced with the generic
"wide-bore vs short-bore, 1.5T vs 3T" framing; vendor channel counts kept only as generic examples ("a
multichannel head coil", "a spine array") since the specific channel numbers are vendor-illustrative, not
board facts; keep the physics terms (B0, B1, shim, gradient, RF, SAR, B1+rms, magic angle, fill factor,
CP = circularly polarized) as standard. No site names, phone numbers, or "available at X" locations.

Kept as generally true (physics/ARRT-consistent):
- **Coil physics:** B0 = main field coil; shim coils improve field homogeneity; gradient coils vary the
  field with position for spatial encoding (X = R/L, Y = A/P, Z = H/F); the RF transmit coil produces the
  B1 field perpendicular to B0 to tip protons; receive/surface coils detect the MR signal.
- **Coil types:** transmit-only (in the bore wall); receive-only (surface coils placed on the patient:
  head/neck, spine, foot/ankle, shoulder, wrist, body phased array) which can be combined; transmit-
  receive (T/R) coils such as a circularly polarized head coil, a knee coil, or the inherent body coil,
  which need a T/R switch and **cannot be combined with any other coil**. A T/R coil gives lower heating
  risk and is preferred for some implant/safety cases. More coil elements = more concentrated sensitivity
  and higher SNR over a local region; fewer elements = more noise. Receive-array advantages: high SNR,
  faster scans (parallel imaging), coverage; disadvantages: wrap/aliasing and burn risk.
- **Fill factor:** how much of the coil's sensitive volume the anatomy occupies; a higher fill factor
  (coil fitted closely to the part) improves SNR and image quality.
- **Positioning:** center a head coil at the glabella for brain, the chin for spine; body array over the
  area of interest with the part within the spine coil, pelvis array top at the iliac crest; knee coil
  centered at the inferior patella; do not angle the wrist coil more than 54.7 degrees or magic-angle
  artifact degrades tendon/ligament T2 signal; combining coils for multi-station protocols (brain+spine,
  Achilles = foot/ankle + spine, brachial plexus, runoff, abdomen/pelvis).
- **Safety / RF heating:** SAR = RF power absorbed per kg (W/kg), depends on habitus/weight/tissue and
  sequence, and roughly quadruples from 1.5T to 3T; normal mode < 2 W/kg whole body (< 3.2 W/kg head),
  first level < 4 W/kg whole body. Reduce SAR: lower flip angle, low-SAR RF pulse, reduce turbo/echo-train,
  fewer slices, more concatenations, remove unneeded sat bands. B1+rms is the patient-independent average
  RF field (µT) the system reports and tracks tissue heating more precisely than SAR percentage; certain
  implants (for example a DBS with whole-body eligibility) require sequences at or below a stated B1+rms
  limit such as 2 µT, checked before each sequence. Burn prevention: never let the patient touch the bore
  or bare coil/cable, pad skin-to-skin contact (crossed hands/feet, bilateral hip/knee implants), confirm
  the entered height and weight (SAR depends on it), and consider 1.5T when a metal implant causes severe
  artifact or requires a lower field.

## Content to add

1. **Lesson 1 — "MRI coils: field coils, RF coil types, and coil selection"** —
   `{topic:"instrumentation", kind:"education"}`, all six body fields. The coil chain (B0, shim, gradient,
   RF transmit, receive); transmit-only vs receive-only vs transmit-receive and the cannot-combine rule;
   coil elements and fill factor; selecting and combining coils. exam_traps: a T/R coil (CP head, knee,
   inherent body) cannot be combined with any other coil; gradient coils do spatial encoding, they do not
   transmit RF.
2. **Lesson 2 — "Coil positioning by region: landmarks and setup"** —
   `{topic:"procedures-anatomy", kind:"education"}`, all six body fields. Head coil glabella (brain) vs
   chin (spine); body array over the part with the part in the spine coil and the pelvis array at the
   iliac crest; knee at the inferior patella; the 54.7-degree magic-angle limit on the wrist coil; multi-
   coil protocols. exam_traps: wrist coil angled past 54.7 degrees causes magic-angle artifact in tendons;
   center the head coil at the glabella for brain and the chin for spine, not one landmark for both.
3. **Lesson 3 — "RF heating and coil safety: SAR, B1+rms, and burns"** —
   `{topic:"safety", kind:"education"}`, all six body fields. SAR definition/units/modes and the 1.5T-to-3T
   quadrupling, reduce-SAR levers; B1+rms and the implant (DBS 2 µT) eligibility check; burn prevention
   (no bore/coil contact, pad skin-to-skin, confirm height/weight) and the implant-artifact 1.5T option.
   exam_traps: SAR roughly quadruples (not doubles) from 1.5T to 3T; B1+rms is patient-independent and
   system-reported, unlike SAR.
4. **~20 quiz items** split ~7 `instrumentation` (B0/shim/gradient/RF roles; gradient axes R-L/A-P/H-F;
   transmit-only vs receive-only vs T/R; T/R cannot combine; more elements = higher SNR; fill factor;
   receive-array pros/cons) + ~7 `procedures-anatomy` (glabella vs chin centering; knee at inferior
   patella; pelvis array at iliac crest; body part within the spine coil; wrist 54.7-degree magic-angle
   limit; combining coils for brain+spine / Achilles / runoff; body array indications) + ~6 `safety` (SAR
   units/definition; normal-mode 2 W/kg limit; 1.5T-to-3T quadrupling; a reduce-SAR lever; B1+rms is
   patient-independent; DBS B1+rms limit / T/R coil lower heating; burn prevention). Four balanced-length
   options, no em dashes, no AI tells.

Voice per [[feedback_no_ai_tells_content]].

## Integration, testing, edge cases

Same pipeline as phase 2: Fable author writes `{lessons:[3], quiz:[~20]}` → Fable accuracy review
(physics-correct, fully generalized, plausible distractors, balanced lengths, no dashes) → controller
appends to `data/course_content.json` (fresh ords after global max, byte-stable `quiz_length_tools.dump`)
→ bump `tests/test_course_depth.py` count 27 → 30 → guard + depth + images tests green + `ruff check src/
tests/` → idempotent MCP reseed by `body->>'title'`/`prompt`. No JS/engine change. Branch off fresh main
after #397 (phase-2 Body) merges so the baseline is 378 items / depth 27. Edge cases: answer-length tell
(guard), duplicate prompt/title (applier + reseed not-exists guard), generalization miss (accuracy
reviewer), depth-count drift (bump the two `27`s to `30`).

## Out of scope

- Any `course.js` / curriculum-map change (all three topics already mapped).
- Image-based questions (text only here).
- Scanner-model spec tables and QC/phantom/registration deck pages (vendor-specific, not board content).
- The B0/B1/gradient theory beyond coil roles (covered by existing physics modules).
