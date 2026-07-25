# Course study rail — design

**Goal:** Fill the empty right-hand gutter on the course page (`web/course.html`) on wide screens
with a sticky **study rail** — a contextual "do next" action panel for the current topic — so that
whitespace becomes a study cockpit instead of looking accidental. The reading column stays capped
(legibility unchanged); the rail is desktop-only surplus that hides on narrow screens.

**Audience:** learners working through the course. **Success:** on a topic view at ≥1100px, the
learner can, without scrolling or hunting, jump into the simulator on this topic, practice its
quiz, jump to the course questions, see topic progress, and move to the next/previous topic.

## Context (what exists)

- `web/course.html` layout: `.course { display:grid; grid-template-columns: 288px 1fr }`;
  `.main { max-width:780px }` is **left-anchored** in the `1fr` track, so slack piles on the right.
- The **left** `.rail` already lists the active module's education cards + lessons as anchored,
  checkable sub-items with progress — so the right rail must NOT be a second lesson list.
- `renderTopic(main, mod, lessonsByTitle, premiumByTopic)` (`course.js:573`) builds a topic view:
  education `.edu` cards (`id="edu-<slug>"`), a Lessons `.sec`, a premium quiz `.sec`
  (`id="quiz-<slug>"`), a free-quiz footer link, and mastery.
- Deep-links that already exist and are reused verbatim: `simulator.html?lesson=<title>`
  (`course.js:1402`), `quiz.html?topic=<topic>` (`course.js:672`), and in-page anchors.
- `TOPIC_CFG[mod.title]` carries `.quiz` (topic names) and `.premium` (keys). `loadDone()` gives
  per-lesson completion. Curriculum order + `CORE_MODULE_COUNT` (`course.js:53`) define topic order.
- Non-topic renderers (`renderOverview`, exam setup/run, placement/diagnostic, review) own the full
  content column and must NOT show the rail.

## Layout & responsiveness

- Grid becomes three columns at ≥1100px: `288px minmax(0, 780px) 240px` (left nav | capped reading
  column | study rail). The reading column keeps its 780px cap — text width never changes.
- **< 1100px:** the third column is dropped; layout returns to `288px 1fr` (and the existing
  ≤780px rule still collapses to one column). The rail element is `hidden` so it takes no space.
- The rail is `position: sticky; top: <header offset>` so it follows a long module; its own content
  is short, so it never needs to scroll internally.

## Where it appears

Only on **topic views**. `buildStudyRail(mod, cfg)` fills `<aside id="studyrail">` at the end of
`renderTopic`; every non-topic renderer calls `clearStudyRail()` (empties + `hidden=true`) so the
rail never shows on Overview, Practice exam, Placement test, Review, or the mastery run.

## Contents (top → bottom)

1. **THIS TOPIC** — module title + a progress line reusing the left rail's count
   (`done / total` lessons) with a slim bar (reuse `.bar`/`.prog` styling).
2. **Actions** (each row omitted when its target doesn't exist):
   - **▶ Open in simulator** → `simulator.html?lesson=<encodeURIComponent(mod.lessons[0])>`.
     Shown when the module has at least one lesson.
   - **Practice: <topic> quiz** → `quiz.html?topic=<encodeURIComponent(cfg.quiz[0])>`.
     Shown when `cfg.quiz.length`.
   - **Jump to course questions** → scrolls `#quiz-<slug(mod.title)>` into view.
     Shown only when premium quiz questions were rendered for this topic.
3. **‹ Prev topic / Next topic ›** — `renderTopic` for the previous/next curriculum module;
   the edge buttons disable at the ends. Order = curriculum order (same as the left rail).

## Wiring

- New `<aside id="studyrail" hidden></aside>` in `course.html`, inside `.course`, after `.main`.
- `course.js`: `buildStudyRail(mod, cfg)` (DOM build via the existing `h()` helper) called at the
  end of `renderTopic`; `clearStudyRail()` called by each non-topic renderer.
- **Pure helpers extracted for testing** (no DOM): `firstLesson(mod)`, `topicNav(curriculum, mod)`
  → `{prev, next}` (by title, null at ends). `buildStudyRail` uses them.
- No new data model, no backend, no new deep-link formats.

## Testing

- Extend `web/course_logic.test.mjs` (Node, no DOM) with cases for `firstLesson` and `topicNav`
  (first/middle/last topic, single-lesson module). Export the helpers for the test.
- `npx eslint web/` clean; `npm run test:web` green.
- Playwright manual: rail renders on a topic with the right links; hides on Overview + Practice
  exam; Prev/Next walks topics and disables at the ends; column drops < 1100px with the reading
  column still capped; sticky through a long module.
- `web/sw.js` cache bump.

## Out of scope

No change to the left rail, reading column width, lesson content, or the simulator/quiz pages; no
new deep-link parameters; no per-lesson simulator list in the rail (one "first lesson" link).
