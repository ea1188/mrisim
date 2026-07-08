# Course content: Body clinical protocols (PDF phase 2, region 5) — Design

**Goal:** Add body (abdominopelvic) MRI content to the paid course — two reading lessons plus ~20 quiz
items — generalized from the "MR Intern Competency" deck's body section (liver, MRCP, screening
abdomen/pelvis, female pelvis), deepening the course's ARRT Procedures coverage. This is the **final**
region of PDF phase 2.

**Status:** Approved 2026-07-08. Fifth and last region of PDF phase 2, following Neuro (#393), Spine
(#394), Neurovascular (#395), MSK (#396). See [[project_pdf_content_phases]].

## Context

Content lives in `data/course_content.json` (source; seeded to Supabase `course_content`, served by
`web/course.js`). Same two existing, already-mapped topics as Neuro/Spine/MSK, so no `course.js` change:

- `procedures-anatomy` — Module 4 (regional anatomy: planes, coverage, positioning by body part). After
  Neuro+Spine+MSK: 4 education + 39 quiz.
- `procedures-protocols` — Module 9 (building a protocol). After Neuro+Spine+MSK: 4 education + 42 quiz.

Item shape `{topic, kind, ord, body}`; education `body` = `{title, html, keypoints, worked_example,
memory_hooks, exam_traps}`; quiz `body` = `{prompt, options[4], answer (0-idx), explain}`. Answer-length
guard forbids a keyed answer exceeding every distractor by >20%. All quiz keyed to index 0 (course.js
shuffles at render, so not a tell). ~20 quiz split 10/10 anatomy/protocols.

## Source & generalization

Source: `pdf education/MR Intern Competency 2025.pdf`, body section (pages 116-132). Generalize:
vendor/brand contrast names → the drug class ("Vueway" → weight-based extracellular gadolinium; "Eovist"
→ a hepatobiliary contrast agent); vendor sequence names → generic ("GRASP" → free-breathing dynamic
contrast-enhanced (DCE) radial acquisition; "PACE" → respiratory-triggered/navigator; "HASTE" →
single-shot fast spin echo; "radial VIBE" → free-breathing radial 3D T1 gradient echo; "VIBE" → a 3D T1
gradient echo); named sites (32nd, 41st, CBI, 6 Ohio, Gramercy) removed; "glucagon/glucogen" → an
antispasmodic (anti-peristaltic) agent. Keep as generic technique terms: proton density fat fraction
(PDFF), MR elastography, MRCP, ampulla of Vater, secretin.

Kept as generally true (ACR-consistent): liver indications HCC, cirrhosis, hemangioma, fatty liver,
hepatitis; phased-array body coil over posterior spine elements; cover the entire liver; extracellular
weight-based gadolinium is the default, a hepatobiliary agent is chosen for focal nodular hyperplasia
(FNH) and the living-liver-donor protocol because hepatocytes take it up and excrete it into bile; a poor
breath-holder is managed with respiratory-triggered or navigator-gated sequences and single-shot / radial
free-breathing acquisitions rather than long breath-holds; PDFF quantifies fat and is run pre-contrast,
used for iron/hemochromatosis and steatosis; MR elastography maps liver stiffness; elastography/donor
patients fast ~4 hours to reduce bowel motion. MRCP: heavily T2-weighted so static bile and pancreatic
fluid are bright; NPO 4-6 hours; a dilute oral agent (water mixed with a small amount of gadolinium) is
swallowed to null (darken) overlapping bowel fluid by shortening its T2 so it does not obscure the ducts;
axial coverage dome of liver to below the ampulla of Vater; indications gallstones, pancreatitis,
pancreatic mass, biliary obstruction. Secretin MRCP: secretin transiently dilates the pancreatic ducts
and stimulates exocrine output, improving duct visualization and dynamic assessment for chronic
pancreatitis, ductal stricture, and obstructing duct stones. Screening abdomen/pelvis: axial top of liver
to below the pubic symphysis, often two overlapping packages; empiric ~30-second delay for routine
post-contrast vs a free-breathing dynamic (DCE) injection with a short inject delay for enterography
(Crohn) and hematuria/bladder work. Renal-mass/screening pelvis covers top of adrenal to pubic symphysis;
enterography covers dome of liver through the anus. Female pelvis: indications fibroids, endometriosis,
adnexal mass/ovarian cyst, cervical pathology, congenital uterine anomaly; fast ~4 hours; head-first
supine with an anterior phased-array coil; straight (unangled) packages by default, but oblique the
small-field-of-view T2 package to the **uterus** for endometrial cancer / congenital uterine anomaly and
to the **cervix** for cervical cancer; an antispasmodic may be given to reduce peristalsis.

## Content to add

1. **Lesson 1 — "Body MRI protocols: liver, MRCP, and abdomen/pelvis coverage"** —
   `{topic:"procedures-anatomy", kind:"education"}`, all six body fields. Per-exam indications, coil and
   positioning, and coverage landmarks (entire liver; MRCP dome-of-liver-to-below-ampulla; screening
   abd/pelvis top-of-liver-to-pubic-symphysis; renal-mass adrenal-to-symphysis; enterography
   liver-to-anus; female pelvis whole pelvic organs). exam_traps: MRCP axial stops below the ampulla of
   Vater, not at the liver dome; screening abd/pelvis is two overlapping packages.
2. **Lesson 2 — "Body MRI technique: contrast agents, breath-hold vs navigator, MRCP, and orientation"** —
   `{topic:"procedures-protocols", kind:"education"}`, all six body fields. Extracellular-vs-hepatobiliary
   contrast choice, poor-breath-holder strategy (respiratory-triggered/navigator + single-shot/radial),
   PDFF pre-contrast and elastography, MRCP heavy T2 + oral negative contrast + secretin, empiric-delay
   vs dynamic-DCE timing, and female-pelvis orientation (straight default; oblique to uterus for
   endometrial/congenital, to cervix for cervical cancer). exam_traps: hepatobiliary agent (not
   extracellular) for FNH and the donor protocol; oral agent in MRCP darkens bowel fluid, it is not the
   IV contrast.
3. **~20 quiz items** split ~10 `procedures-anatomy` (liver indications; entire-liver coverage; body
   phased-array positioning; MRCP dome-to-below-ampulla coverage; screening abd/pelvis
   liver-to-symphysis; renal-mass adrenal-to-symphysis; enterography liver-to-anus coverage; female-pelvis
   indications; female-pelvis head-first-supine anterior coil; fast-4-hours prep) and ~10
   `procedures-protocols` (extracellular gadolinium default; hepatobiliary agent for FNH/donor;
   poor-breath-holder navigator/triggered; PDFF pre-contrast for iron; elastography for stiffness; MRCP
   heavily T2-weighted; oral negative contrast darkens bowel fluid; secretin dilates pancreatic ducts;
   empiric 30 s delay vs dynamic DCE for enterography; orient to uterus vs cervix by cancer type). Four
   balanced-length options, no em dashes, no AI tells.

Voice per [[feedback_no_ai_tells_content]].

## Integration, testing, edge cases

Same pipeline as prior regions: Fable author writes `{lessons:[2], quiz:[~20]}` → Fable accuracy review
(ACR-consistent, fully generalized, plausible distractors, balanced lengths, no dashes) → controller
appends to `data/course_content.json` (fresh ords after global max, byte-stable `quiz_length_tools.dump`)
→ bump `tests/test_course_depth.py` count 25 → 27 → guard + depth + images tests green + `ruff check src/
tests/` → idempotent MCP reseed by `body->>'title'`/`prompt`. No JS/engine change. Edge cases:
answer-length tell (guard), duplicate prompt/title (applier + reseed not-exists guard), generalization
miss (accuracy reviewer), depth-count drift (bump the two `25`s to `27`).

## Out of scope

- Phase 3 (Coil selection & positioning) — future sub-project; completes phase 2.
- Any `course.js` / curriculum-map change (both topics already mapped).
- Image-based questions (text only here).
- Weekly-QC / phantom / patient-registration deck pages (133+) — site-operational, not board content.
