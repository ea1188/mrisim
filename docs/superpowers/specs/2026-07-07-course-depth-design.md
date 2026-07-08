# Course Module Depth (Phase 2) — Design

**Goal:** Turn each of the 16 premium education modules from a tight "exam synthesis" blurb
into substantive study material by adding a worked example, memory hooks, and common-exam-trap
notes for ARRT registry candidates and new MRI technologists.

**Status:** Approved 2026-07-07. Format = structured fields (not inline HTML expansion, not
separate cards). Quantity per module = 1 worked example, 2–3 memory hooks, 2–3 exam traps.
Rendered on the course "Course material" cards only (not the illustrated lesson viewer).

## Context

Each of the 16 `kind:"education"` items in `data/course_content.json` currently has a `body`
with `title`, `html` (~150–250 words), and `keypoints` (5). The bodies live in Supabase
(`course_content`, RLS-gated); `data/course_content.json` is the source, re-seeded to the DB by
`scripts/seed_course_content.py` (idempotent: deletes the course's rows, re-inserts from JSON).
The `body` column is jsonb, so the whole object is stored — **new body fields need no schema
migration.** The browser reads education bodies via `Accounts.premiumContent` into `CTX.byTopic`
and renders them in `course.js` `renderTopic` (the "Course material" section, ~lines 352–378).

Phase 1 (mastery checks) shipped, so each module's mastery check now gates on the module. Phase 2
makes the modules worth mastering.

## Architecture

Three new optional fields per education `body`, rendered as labeled sections in `course.js`,
authored by parallel agents with a domain-accuracy review gate, then re-seeded to Supabase. No
backend schema change, no new content-type, no service-worker cache bump (`course.js`/`course.html`
are network-first SHELL files).

## Data model

Each education `body` in `data/course_content.json` gains (all optional, backward-compatible):

```json
{
  "title": "…", "html": "…", "keypoints": ["…"],
  "worked_example": "<p>…one short HTML scenario that walks the reasoning…</p>",
  "memory_hooks": ["short mnemonic or memory device", "…"],
  "exam_traps": ["the classic registry mistake / don't confuse X with Y", "…"]
}
```

- `worked_example`: a string of trusted premium HTML (rendered with `html:`, like the existing
  `body.html`). Exactly one per module. A concrete, specific scenario that applies the module's
  concept and shows the reasoning to an answer.
- `memory_hooks`: array of 2–3 short plain-text strings (rendered as `<li>` via `text:`).
- `exam_traps`: array of 2–3 short plain-text strings (rendered as `<li>` via `text:`).

A module missing any field simply does not render that block. All 16 modules will be populated in
this phase.

## Rendering (`course.js` `renderTopic`, education card)

Between the existing Key points block and the `edu-foot` (read footer), append — only when the
field is present and non-empty — in this order:

1. **Worked example** — `<div class="edu-worked">` with an `<h5>Worked example</h5>` and the HTML
   via `html:`.
2. **Memory hooks** — `<div class="edu-hooks">` with `<h5>Memory hooks</h5>` and a `<ul>` of the
   strings via `text:`.
3. **Exam traps** — `<div class="edu-traps">` with `<h5>Exam traps</h5>` and a `<ul>` of the
   strings via `text:`.

Styling in `web/course.html`: distinct labeled sub-blocks (mono uppercase eyebrow headings like
the existing `.sec h3`; the worked example gets a subtle left rule / panel; traps get a muted
warning-tone accent). Consistent with the flat/clinical aesthetic — no emoji, no gradient, no
pills. These blocks are part of the read card, so the existing "Mark as read" still governs
completion (no change to subsection/mastery tracking).

## Content standards

- **Accuracy is the primary risk.** Every field must be factually correct MRI physics / safety /
  procedure content, grounded in the specific module's topic. Each batch gets a dedicated
  domain-accuracy review (the same rigor as the 205-question quiz audit): worked example reasoning
  is sound, memory hooks are correct and not misleading, exam traps describe real registry-level
  confusions.
- **No em dashes and no AI-tell punctuation** in any field (extends
  `[[feedback_no_ai_tells_content]]`). Natural prose.
- Audience: ARRT candidates + new techs. Concrete, exam-relevant, not padded.
- Display name "MRISim"; professional/clinical tone.

## Data flow / deployment

1. Edit `data/course_content.json` (add the three fields to each education body).
2. Owner runs `SUPABASE_URL=… SUPABASE_SERVICE_ROLE=… python scripts/seed_course_content.py` to
   re-seed `course_content` (owner-gated: needs the service_role key, like every DB step; the
   agents/plan produce the JSON + render code but do NOT run the seed).
3. `course.js`/`course.html` deploy via the normal Pages workflow on merge; no cache bump.

## Execution (subagent-driven)

The 16 modules are independent, so this parallelizes well:
- **Content tasks:** batches of 4 modules; one implementer agent per batch writes the three fields
  into those modules' bodies in `data/course_content.json`. A reviewer per batch verifies
  accuracy + no-AI-tells + schema/type correctness.
- **Render task:** one task adds the three blocks to `course.js` `renderTopic` + CSS to
  `course.html`.
- **Validation task:** adds a check that asserts every education body has `worked_example`
  (non-empty string), `memory_hooks` (list of 1–3 strings), `exam_traps` (list of 1–3 strings),
  and that no field contains an em dash. Runs locally and in CI.

## Testing

- **Data validation** (python, no network): loads `data/course_content.json`, asserts every
  `kind:"education"` body has the three fields with correct types and non-empty content, and that
  no depth field (or html/keypoints) contains an em dash / en dash. Fast; runs locally and in CI.
- **Render:** `npm run lint` clean on `course.js`; the blocks render only when present
  (backward-compatible); manual signed-in view confirms the three sections appear under a module
  with correct styling.
- No engine/physics change, so the Python test suite is unaffected.

## Out of scope (later phases)

- Figures/diagrams and image-based questions (Phase 3/4).
- Server-side progress sync.
- Any change to the mastery-check or quiz mechanics.
- Running the Supabase seed (owner-gated credential step).
