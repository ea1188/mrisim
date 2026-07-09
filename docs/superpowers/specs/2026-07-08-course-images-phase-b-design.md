# Exam-realistic image questions — Phase B: owner-supplied image bank + wire-in — Design

**Goal:** Build the rails so the course owner can drop in their own (or genuinely license-free) clinical
images and have the matching image question surface immediately, with no external-license footprint. Phase B
delivers: (1) `Owner-Original` support in the schema (owner-owned images need no attribution and show no
caption), (2) a precise image requirements list ("shopping list") of every question that needs an image and
exactly what it must show, and (3) the questions fully drafted so each supplied image drops into a ready
slot. No images are sourced from outside; the course stays fully owner-controlled and trustworthy.

**Status:** Approved 2026-07-08. Workflow pivoted from external sourcing to **owner-supplied**: I produce
the list + wire-in support; the owner obtains each image (their own or truly public-domain); I attach it and
surface the question. Until an image arrives, its concept stays as its clean text-only question, so the
course is always shippable.

## Context

Phase A (PR #404, `main` @f2912aa) shipped the rail this fills:
- A `kind:"quiz"` body carries exactly one image source: `setup` (simulator) XOR `credit`
  `{author, license, source_url, title}` (curated image). Guarded by `tests/test_course_images.py`
  `validate_image_body` (XOR + commercial-safe license allow-list + image-exists).
- `web/course.js` `addQImg` renders an attribution caption `Image: <author> · <license> · source` beneath a
  `credit` image; `scripts/prerender_course_quiz.py` skips `credit` items (they ship as committed files).
- Live content is served from Supabase `course_content` (course `mri-core`); any content edit must be
  RESEEDED there, not just committed.
- Phase A converted 8 questions to text-only (3 pathology, spin-echo/ghosting/susceptibility, fat-sat pair);
  Phase B re-adds image versions for the ones an image genuinely helps, plus new artifact image-IDs.

## `Owner-Original` schema support

Owner-owned images carry no third-party rights, so they need no attribution and no source link. Add an
`Owner-Original` value handled specially:
- **Allow-list:** `tests/test_course_images.py` `ALLOWED_LICENSES` gains `Owner-Original` (kept alongside the
  commercial-safe set `CC0-1.0` / `Public-Domain` / `CC-BY-4.0/3.0/2.0` for a genuine public-domain image the
  owner might find; `-NC`/`-ND` remain excluded).
- **Relaxed validation:** for `license == "Owner-Original"`, a `source_url` is NOT required (the owner is the
  source); `title` is still required, `author` defaults to the course owner (e.g. `"MRISim"`). For any
  external license, `author` + `source_url` + `title` remain required, as in Phase A.
- **Suppressed caption:** `addQImg` renders NO attribution caption when `license == "Owner-Original"` (you do
  not cite yourself); the image shows clean. External-licensed images still get the Phase A caption.
- **credits.html:** the "Course question images" policy line notes that clinical images are either owned by
  the course or openly licensed, and that images are shown resized.

## The image requirements list (the "shopping list")

Ten slots. Each names the image type and the finding that must be clearly, unambiguously visible (get a
clean textbook example the owner has the right to use). Items 1-6 restore Phase-A concepts; 7-10 add new
registry image-IDs. Target filenames follow the existing `cq-*` convention.

| # | Concept · topic | Image type | Must clearly show | Target file | Wiring |
|---|---|---|---|---|---|
| 1 | Acute infarct · pathology | Axial brain DWI (b~1000), matched ADC if available | Focal bright restricted-diffusion lesion (dark on ADC) | `cq-infarct-dwi-01.jpg` | upgrade ord 914 |
| 2 | Enhancing tumor · pathology | Axial post-contrast T1 brain | Mass with abnormal ring/solid enhancement | `cq-tumor-postgad-01.jpg` | upgrade ord 916 |
| 3 | Hemorrhage / microbleeds · pathology | Axial SWI or GRE brain | Focal dark blooming signal dropout from blood products | `cq-hemorrhage-swi-01.jpg` | upgrade ord 915 |
| 4 | Multiple sclerosis · pathology | Axial/sagittal FLAIR brain | Periventricular white-matter plaques (Dawson's fingers) | `cq-ms-flair-01.jpg` | NEW question |
| 5 | Fat suppression OFF · fat-suppression | T1/PD MSK/orbit/neck, no fat-sat | Bright subcutaneous + marrow fat | `cq-fatsat-off-01.jpg` | upgrade ord 912 |
| 6 | Fat suppression ON · fat-suppression | Same region/sequence with fat-sat (STIR ok), matched to #5 | That fat now dark | `cq-fatsat-on-01.jpg` | upgrade ord 913 |
| 7 | Motion / flow ghosting · flow-artifacts | Any sequence with real ghosting | Discrete repeating ghosts along the phase-encode axis | `cq-ghosting-01.jpg` | upgrade ord 910 |
| 8 | Chemical shift artifact · image-quality | GRE / high-field at a fat-water border | Dark/bright misregistration band at a fat-water interface | `cq-chemshift-01.jpg` | NEW question |
| 9 | Gibbs / truncation · image-quality | T2 sagittal spine (classic) or brain | Parallel ripple lines near a sharp high-contrast border | `cq-gibbs-01.jpg` | NEW question |
| 10 | Aliasing / wrap-around · image-quality | Any image with FOV too small | Anatomy wrapped from one edge onto the other | `cq-aliasing-01.jpg` | NEW question |

"upgrade ord N" = the concept already exists as a Phase-A text question; supplying its image adds `img` +
`credit` to that row (no rewrite needed if the finding matches). "NEW question" = drafted here, added to
`course_content.json` as an image question when its image arrives.

The four NEW-question drafts (MS FLAIR, chemical shift, Gibbs, aliasing) are written out in full (prompt, 4
options, index-0 keyed answer, explanation), option lengths balanced for the answer-length guard, and held
in the plan/manifest ready to drop in.

## Workflow (per supplied image)

1. Owner obtains an image matching a slot (their own or genuinely license-free) and provides the file.
2. I place it at `web/img/course-quiz/<target file>` (resized to <=600px wide, JPEG q85 if needed).
3. I set the question's `credit` (`Owner-Original` unless the owner specifies a public-domain source) and
   `img`; for a NEW slot I add the drafted question; for an upgrade I add `img`+`credit` to the existing row.
4. Verify: the image genuinely shows the finding the answer asserts (accuracy gate).
5. Byte-stable `course_content.json` via `scripts/quiz_length_tools.py`; reseed the changed Supabase rows;
   guards; the question goes live with a clean (uncaptioned) owner image.

## Scope of THIS phase (the PR)

Phase B's committed deliverable is the **rail + the list**, not the images (which arrive later, ad hoc):
- `Owner-Original` support (guard allow-list + relaxed validation + `addQImg` caption suppression).
- The requirements list committed as a working manifest doc the owner can reference.
- The four NEW-question drafts written and held ready.
- credits.html policy line updated.
No live curated images ship in this PR (there are none yet); each supplied image is a small follow-up
wire-in (steps above), not a re-plan.

## Testing & guards

- `tests/test_course_images.py`: `Owner-Original` accepted; `source_url` optional for it and required for
  external licenses; XOR + file-exists + unique filenames still hold. Add unit cases for the relaxed
  `Owner-Original` validation and the still-strict external-license validation.
- Any NEW drafted question, once added with an image, must pass `tests/test_quiz_length.py` (keyed answer not
  the sole longest) — draft option lengths accordingly.
- Full `pytest` (python3.11), `npm run test:web`, `ruff check src/ tests/`, `eslint web/` before PR.
- `addQImg` caption logic: a small check that `Owner-Original` renders no caption while an external license
  does (course.js is not a module; verify by code review + the Phase A behavior for external credit).

## Out of scope

- **External image sourcing** (Wikimedia/Open-i pipeline) — dropped in favor of owner-supplied; the
  allow-list still permits CC0/PD/CC-BY if the owner ever chooses one, but the workflow does not fetch.
- **Annotated/derivative images** — owner supplies finished images; we resize only.
- **Expanding the simulator-rendered physics set / thin-topic balancing** — Phase C.
- Any change to entitlements, mock-exam sampling, the free quiz, or the `setup`/`credit` core schema.

## Edge cases

- **No image supplied for a slot:** it stays as its Phase-A text-only question indefinitely; no gap, no
  broken image.
- **Owner-Original with no source_url:** allowed (owner is the source); external license without a
  source_url is rejected by the guard.
- **Supplied image does not clearly show the finding:** rejected at the accuracy gate; owner supplies a
  clearer one or the question is reworded to what the image shows.
- **Filename already used by a sim image:** the `cq-fatsat-off/on` names were freed in Phase A (converted to
  text); reusing them for the owner images is fine and keeps the convention.
