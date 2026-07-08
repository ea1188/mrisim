# Premium Image-Based Questions (Phase 3.1) — Design

**Goal:** Add engine-rendered "look at this scan and answer" questions to the exclusive premium
bank, shown in the course quiz and mastery checks. The differentiator vs text-only registry banks.

**Status:** Approved 2026-07-07. First batch ~16 questions on image-heavy topics. Image questions
join the existing mastery-check + practice-exam pools automatically (they are quiz items). A visual
verification pass (controller opens each rendered image against its keyed answer) is a required gate.

## Context

`course.html` runs NO engine (static: config/accounts/course_logic/course.js). The course lesson
viewer already shows pre-rendered, committed images (`web/img/lessons/<slug>/<n>.jpg`, built by
`scripts/prerender_lessons.py` via `web_adapter` render). The free read-the-scan quiz (`quiz.html`)
renders live and its items carry a `setup` render payload. Premium quiz items (`data/course_content.json`,
`kind:"quiz"`, served from Supabase `course_content`) currently have `body = {prompt, options, answer,
explain}` — text only. `course.js` renders them inline (`quizItem`) and samples them into the
per-module mastery check + the whole-bank practice exam.

## Architecture

An image question is a premium quiz item with two optional body fields added: a render `setup` and an
`img` filename. `scripts/prerender_course_quiz.py` renders each `setup` via the engine to a committed
JPEG under `web/img/course-quiz/`, mirroring `prerender_lessons.py`. `course.js` shows the image above
the prompt wherever a premium quiz item is rendered (inline quiz + mastery check). No engine in the
course page; no Supabase schema change (jsonb body). Backward-compatible: items without `img` stay
text-only.

## Data model (premium quiz `body`, added fields; both optional)

```json
{
  "prompt": "...", "options": ["..."], "answer": 0, "explain": "...",
  "setup": { "region": "Brain", "orientation": "axial", "slice_idx": 90,
             "params": { "sequence": "Spin Echo", "TR": 500, "TE": 12 }, "pathology": "stroke" },
  "img": "cq-weighting-t1-01.jpg"
}
```

- `setup`: the render payload, identical in shape to the free read-the-scan quiz `setup`
  (`region`, `orientation`, `slice_idx`, `params{...}`, optional `pathology`). Used ONLY by the prerender
  script; the browser ignores it.
- `img`: a filename (kebab-case, `.jpg`). The browser displays `img/course-quiz/<img>`. Prefix `cq-`
  to keep the namespace obvious.

Valid `setup` catalog (from `web/quiz.json`, proven to render): T1 SE (`TR 500/TE 12`); T2 SE
(`TR 3500/TE 110`); FLAIR (`Inversion Recovery`, `TI 2548`); TOF (`MR Angiography`, `angio_type TOF`);
DWI + `pathology:"stroke"` (`Diffusion (DWI)`, `diff_display DWI`, `b_value 1000`); SWI +
`pathology:"hemorrhage"`; tumor + `contrast_enabled`; motion artifact (`motion_enabled`); fat-sat
(`fatsat_enabled`). Content authors pick a `setup` whose rendered image genuinely shows what the
question asks.

## Components

1. **Render + CSS** (`web/course.js`, `web/course.html`): where a premium quiz item is rendered, if
   `body.img` is present, prepend `<img class="q-img" src="img/course-quiz/<img>" alt="Scan for this
   question">`. Two render sites: `quizItem` (inline "Test yourself") and the mastery-check question
   renderers (`renderMasteryRun` and the review list in `renderMasteryResult`). CSS: a bounded,
   centered image block consistent with the flat/clinical look.
2. **Prerender script** `scripts/prerender_course_quiz.py`: load `data/course_content.json`; for every
   `kind:"quiz"` item whose body has both `setup` and `img`, build the render payload, call
   `web_adapter` render (reuse the host + region handling from `prerender_lessons.py`), and write
   `web/img/course-quiz/<img>` as JPEG. Idempotent; committed (not wired into CI — needs
   numpy/matplotlib/Pillow, like the lessons prerender).
3. **Content**: ~16 new premium quiz items in `data/course_content.json` across image-heavy topics
   (contrast-weighting, pulse-sequences, image-quality, flow-artifacts, fat-suppression, pathology),
   each with `prompt/options/answer/explain` + `setup` + `img`. Authored by MRI-expert agents;
   accuracy-reviewed. The `setup` must produce an image that actually supports the keyed answer.
4. **Seed**: owner re-seeds `course_content` (image items included) via `scripts/seed_course_content.py`
   or the MCP path used for Phase 2. Image files are public (the picture is not secret; the gated
   premium content is the Q&A + explanation, exactly as the lesson images are already public).

## Data flow / deployment

1. Author image-quiz items in `data/course_content.json` (with `setup` + `img`).
2. Run `.venv/bin/python scripts/prerender_course_quiz.py` -> generates + commits
   `web/img/course-quiz/*.jpg`.
3. **Visual verification (required gate):** open each generated image and confirm it matches its
   question's keyed answer. Fix the `setup` (or the answer) and re-render for any mismatch.
4. `course.js`/`course.html` deploy via Pages on merge (network-first SHELL, no cache bump; the images
   are new files, fetched normally).
5. Owner re-seeds `course_content` so the DB carries the new items.

## Testing

- **Pure data test** (`tests/test_course_images.py`, pytest, in CI): every `kind:"quiz"` body that has
  `img` also has a `setup` with the required keys (`region`, `orientation`, `params`), and the file
  `web/img/course-quiz/<img>` exists on disk (no broken image reference). No engine needed.
- **Render:** `npm run lint` clean on `course.js`; image renders only when `body.img` is set
  (backward-compatible); manual signed-in view confirms the image appears in the inline quiz and in a
  mastery check.
- The prerender script is exercised by actually running it in the build task (it renders all ~16); no
  separate unit test (matches `prerender_lessons.py`, which has none and is not in CI).

## Execution (subagent-driven)

- **Task: render + CSS** (mechanical) — Fable.
- **Task: prerender script** (mechanical, mirrors `prerender_lessons.py`) — Fable.
- **Task: content** (~16 image questions, accuracy-critical) — Sonnet author + Sonnet accuracy review.
- **Controller step (not an agent task):** run the prerender to generate/commit the images, then the
  visual verification pass (open each image against its answer), fixing setups as needed.
- **Task: data validation test** — Fable.

## Out of scope (later Phase 3 sub-projects)

- Diagnostic pre-test; spaced review of missed items.
- Live in-course engine rendering (deliberately avoided; images are pre-rendered).
- Any change to mastery-check or exam mechanics beyond showing an image on a question.
