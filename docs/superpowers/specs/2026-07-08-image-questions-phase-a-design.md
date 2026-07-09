# Exam-realistic image questions — Phase A: foundation + honesty fix — Design

**Goal:** Establish the schema and attribution plumbing for a two-source image-question bank
(simulator-rendered for physics, curated commercial-safe images for pathology/artifacts), and correct
the existing image questions so every image faithfully and distinctly represents the concept it tests.
Phase A does this WITHOUT any external image sourcing — it is fully in-repo and deterministic. Sourcing
the curated bank is Phase B; expanding the simulator-rendered set is Phase C.

**Status:** Architecture + A->B->C phasing approved 2026-07-08. Licensing bar for curated images (Phase B):
commercial-safe only (CC0 / public-domain / CC-BY). Sourcing workflow (Phase B): I source + license-verify
+ stage, user approves each batch. This spec covers **Phase A only**.

## Context

MRISim's paid course (course.js, entitlement-gated) shows premium image questions. Each image-question is
a `kind:"quiz"` item in `data/course_content.json` whose `body` has an `img` filename and a `setup` (a
simulator render payload). `scripts/prerender_course_quiz.py` renders each `setup` at build time (via
`src/web_adapter.py` / `src/simulator.py`) to `web/img/course-quiz/<img>.jpg`; course.js `addQImg` shows
`img/course-quiz/<img>` above the prompt. There are currently **17** image questions.

**Two live defects, both traced to the shared-setup render model:**

1. **Duplicated images.** Several questions carry near-identical `setup`s and therefore render the SAME
   image. Confirmed by content hash: one identical T1-SE-brain image backs the *T1 weighting*, *clean
   quality*, *spin echo*, AND *fat-sat off* questions; the *hemorrhage-SWI* and *flow-susceptibility*
   questions share one image; *motion-artifact* and *flow-ghosting* share another. So ~12 unique images
   do 17 jobs, and some images cannot actually support their question (e.g. *fat-sat off* shows a brain,
   which has almost no fat to suppress).

2. **Mislabeled pathology.** The simulator's phantom contains no stroke, tumor, or hemorrhage, so the
   three "pathology" image questions (*acute infarct on DWI*, *SWI hemorrhage*, *enhancing tumor*) render
   a NORMAL brain phantom while the prompt claims the image shows the pathology. This is an accuracy
   defect currently live in the paid product.

`web/credits.html` is hand-authored static HTML (147 lines) with an "Anatomical datasets" section; there
is no credits generator.

## Architecture — one schema, two image sources

The presence of `setup` vs a new `credit` block on a quiz body is the source discriminator:

- **Sim-rendered (`setup` present):** rendered at build time by `prerender_course_quiz.py`. Used ONLY for
  concepts the simulator is ground-truth for — weighting (T1/T2/PD/FLAIR), TR/TE effects, fat-sat on/off,
  SNR, resolution, TOF/PC angiography, aliasing/chemical-shift. Each concept must have a DISTINCT setup
  that faithfully shows it.
- **Curated (`credit` present, no `setup`):** a real image committed under `web/img/course-quiz/` with a
  `credit` block. Used for what the simulator cannot fabricate — real pathology and real-world artifacts.
  **Introduced and populated in Phase B; Phase A only builds the rails.**

**`credit` block shape** (on a quiz `body`, alongside `img`):
```json
"credit": { "author": "Jane Doe", "license": "CC-BY-4.0", "source_url": "https://commons.wikimedia.org/...", "title": "Axial DWI acute infarct" }
```
`license` is restricted to `CC0-1.0` / `Public-Domain` / `CC-BY-4.0` (and CC-BY point variants) — the
commercial-safe set. An item with a `credit` MUST NOT have a `setup` (and vice-versa); this invariant is
checked by a guard test.

**Attribution at the point of use.** `addQImg` in course.js renders a small caption beneath a curated
image: `Image: <author> · <license> · source` (source linking to `source_url`). This is the primary
CC-BY-compliance mechanism (attribution accompanies the work). Sim-rendered images (no `credit`) get no
caption, exactly as today.

**Consolidated credits.** `web/credits.html` gains a short "Course question images" subsection stating the
images are individually CC0/PD/CC-BY and credited beneath each image in the course, plus a maintained list
that grows as Phase B adds images. (No HTML generator; the list is edited alongside the content, same as
the existing "Anatomical datasets" entries.)

## Phase A scope (no external sourcing)

1. **Schema + guard.** Define the `credit` block; add a guard test asserting: every `kind:"quiz"` body has
   at most one of `setup` / `credit`; every `credit.license` is in the commercial-safe allow-list; every
   `img` referenced by a body exists under `web/img/course-quiz/` OR has a `setup` (renderable). This guard
   lives with the existing content guards and runs in CI.
2. **`prerender_course_quiz.py`:** skip items that have a `credit` and no `setup` (do not attempt to render
   curated images; they ship as committed). No behavior change for `setup` items.
3. **course.js `addQImg`:** when `body.credit` is present, append the attribution caption (flat, muted,
   `source` is a link). Pure-ish; the caption-building is factored so it can be unit-tested.
4. **Honesty fix of the existing 17** (audit each; disposition per item):
   - **Physics/parameter concepts the simulator CAN show** (weighting, TR/TE, fat-sat, SNR, resolution,
     angio, aliasing): give each a DISTINCT, correct `setup` and re-render, so no two questions share an
     image and each image visibly demonstrates its concept. Specifically, fat-sat off/on must be rendered
     on a FATTY region (e.g. orbit or knee) with identical params except the fat-sat flag, so the only
     visible difference is fat suppression.
   - **Concepts the simulator CANNOT faithfully show** (the 3 mislabeled pathology questions, and any
     artifact question whose only faithful depiction needs real anatomy): convert to **text-only** in
     Phase A — remove `img` and `setup`, rephrase the prompt to not reference "the image/scan shown."
     The concept stays tested; the false image is gone. Phase B re-introduces an image version backed by a
     real curated image.
   - Every retained/re-rendered image passes an **accuracy review**: the image genuinely and distinctly
     shows the concept the question tests.
5. **credits.html:** add the "Course question images" subsection (rails + wording; the list is empty or
   near-empty in Phase A since no curated images are added yet).
6. **Rebuild + reseed:** run `prerender_course_quiz.py`; dump `course_content.json` byte-stable via
   `scripts/quiz_length_tools.py`; reseed the changed rows to Supabase `course_content`.

## Concept partition (reference for Phases B/C)

- **Simulator owns (sim-rendered):** T1 / T2 / PD / FLAIR weighting; TR/TE effect on contrast; fat-sat
  on/off (fatty region); SNR high/low; resolution/partial-volume; TOF and phase-contrast angiography;
  aliasing/wrap; chemical-shift; basic motion ghosting the flow model produces faithfully.
- **Curated real images own (Phase B):** acute infarct (DWI bright / ADC dark), enhancing tumor
  (post-contrast T1), hemorrhage (SWI blooming), MS periventricular plaques (FLAIR), susceptibility
  artifact on real anatomy, Gibbs/truncation, zipper/RF, dielectric — anything defined by pathology or by
  an artifact on real acquired anatomy the phantom lacks.

## Data flow

```
data/course_content.json  (quiz body: img + setup  OR  img + credit)
        |                                   |
setup -> prerender_course_quiz.py -> web/img/course-quiz/<img>.jpg   (sim, build-time)
credit -> committed image as-is (Phase B); prerender SKIPS
        |
course.js addQImg -> shows <img>; if body.credit, appends attribution caption
        |
guard test (schema/license/img-exists) + accuracy review -> reseed Supabase
```

## Testing & guards

- New guard test (Python, with the existing content guards): the `setup` XOR `credit` invariant, the
  license allow-list, and img-existence. Runs in CI (`ruff`/pytest on src/ + tests/).
- `npm run test:web` / `eslint`: the course.js `addQImg` caption change stays lint-clean; if the caption
  builder is factored into a pure helper, add a small `node --test` for it.
- Re-run `prerender_course_quiz.py` and confirm the previously-duplicated images now differ (content hash).
- Accuracy review (the same discipline used for text content): each retained/re-rendered image faithfully
  and distinctly shows its concept; each converted-to-text question reads correctly without an image.
- Reseed Supabase idempotently; the answer-length balance guard (`tests/test_quiz_length.py`) still passes
  for any reworded prompts (prompts, not options, changed — options/keys untouched where possible).

## Out of scope

- **External image sourcing** (CC0/PD/CC-BY pathology + artifact images, batch approval) — that is **Phase B**.
- **Expanding the simulator-rendered set / balancing thin topics** — **Phase C**.
- **ARRT content-category (blueprint) score mapping** — a separate opportunity, not this feature.
- Any change to entitlements, mock-exam sampling, or the free quiz.

## Edge cases

- **A body with both `setup` and `credit`:** rejected by the guard (must be exactly one image source).
- **Curated `img` missing on disk:** guard fails (a `credit` item must have its committed image present).
- **Re-render determinism:** `prerender_course_quiz.py` is idempotent; re-running must reproduce identical
  bytes for unchanged setups so the diff is limited to the intentionally-changed images.
- **Reworded text questions:** removing `img`/`setup` must not touch `options`/`answer`, so the
  answer-length guard and the index-0 keying convention are unaffected.
