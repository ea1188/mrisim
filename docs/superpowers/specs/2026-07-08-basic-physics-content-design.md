# Course content: MR basic physics fundamentals (PDF phase 5) — Design

**Goal:** Add foundational MR signal-physics content to the paid course — three reading lessons plus ~24
quiz items — generalized from the "Intern Basic Physics part 1" staff deck (generating the MR signal;
T1/T2 relaxation mechanisms; dephasing and spin-echo refocusing). This is **PDF phase 5**, following
phase 1 (contrast reactions, #392), phase 2 (protocols by region, #393-#397), phase 3 (coil/positioning,
#398), and phase 4 (MR parameters, #399).

**Status:** Approved 2026-07-08. Scope ("3 lessons, all detail") chosen by the user. See
[[project_pdf_content_phases]].

## Context

Content lives in `data/course_content.json` (source; seeded to Supabase `course_content`, served by
`web/course.js`). This is the foundational physics beneath the parameter-level content, so it spans three
existing, already-mapped topics. **No `course.js` change** (all three are already in `TOPIC_CFG`):

- `instrumentation` — Module 1 "What an MRI image is" (signal generation: protons, B0, NMV, Larmor, RF,
  resonance, signal induction).
- `contrast-weighting` — Module 2 "Where contrast comes from" (T1 spin-lattice and T2 spin-spin
  relaxation mechanisms, tissue-specific times).
- `pulse-sequences` — Module 6 "How the image is built" (dephasing from field inhomogeneity, T2 vs T2*,
  the spin-echo 180 degree refocusing pulse and TE/2).

Item shape `{topic, kind, ord, body}`; education `body` = `{title, html, keypoints, worked_example,
memory_hooks, exam_traps}`; quiz `body` = `{prompt, options[4], answer (0-idx), explain}`. Answer-length
guard forbids a keyed answer exceeding every distractor by >20%. All quiz keyed to index 0 (course.js
shuffles at render, so not a tell). ~24 quiz split 8 instrumentation / 8 contrast-weighting / 8
pulse-sequences.

**Overlap note (important for authoring):** the course already covers parameter-level T1/T2 and weighting
(phase 4, `contrast-weighting`). This phase must stay at the **mechanism / why** level — the physical
cause of the signal and of relaxation — not re-teach the TR/TE weighting table. Quiz prompts must not
duplicate existing prompts (the applier and reseed guard on exact prompt text; the author must also avoid
near-duplicate questions that only restate a parameter fact already in the bank).

## Source & generalization

Source: `pdf education/Intern Basic Physics part 1.pdf` (37 pages). Generalize: editor/credit names and
external URLs removed. This deck is vendor-neutral physics; keep all standard terms (B0, B1, NMV,
parallel/anti-parallel, precession, Larmor frequency, gyromagnetic ratio, resonance, spin-lattice /
spin-spin relaxation, T1, T2, T2*, dephasing, spin echo).

Kept as generally true (physics/ARRT-consistent):

- **Signal source:** clinical MRI images the hydrogen (1H) nucleus, a single spinning charged proton
  (mainly in water and fat). A spinning charge has a magnetic moment, so it behaves like a tiny bar
  magnet and is affected by an external field.
- **In the field (B0):** protons align parallel (low energy, slight majority) and anti-parallel (high
  energy); the small parallel excess sums to the **net magnetization vector (NMV)** along B0 (the z
  axis). Longitudinal magnetization along B0 cannot be measured directly; it must be tipped into the
  transverse plane.
- **Precession and Larmor:** protons precess about B0 at the Larmor frequency, **fo = gamma x B0**, where
  gamma is the gyromagnetic ratio, **42.58 MHz/T for hydrogen**. Higher field means higher precession
  frequency (e.g. ~63.9 MHz at 1.5T, ~127.7 MHz at 3T).
- **RF excitation (B1):** an RF pulse at (near) the Larmor frequency, applied perpendicular to B0,
  transfers energy by **resonance**, tipping the NMV from longitudinal toward transverse. Off-resonance
  RF does not transfer energy efficiently.
- **Signal:** when RF is off, the rotating transverse magnetization induces a current in the receive
  coil (Faraday induction), which is the MR signal.
- **T1 (longitudinal / spin-lattice) relaxation:** longitudinal magnetization recovers as protons release
  energy as heat to the surrounding lattice. Efficient energy transfer needs the lattice molecular
  motion near the Larmor frequency: free liquids (small, fast molecules) transfer poorly, so **long T1**;
  mid-sized molecules and fat (carbon bonds tumbling near the proton frequency) transfer efficiently, so
  **short T1**. T1 = time to recover **63%** of longitudinal magnetization.
- **T2 (transverse / spin-spin) relaxation:** after excitation, protons dephase because each experiences
  slightly different local fields (from neighbouring spins) and lose phase coherence; transverse
  magnetization decays. T2 = time for transverse magnetization to fall to **37%** of its initial value.
  T2 reflects true spin-spin dephasing; **T2\*** is the faster decay that also includes external field
  inhomogeneity.
- **Ordering and tissues:** **T1 is always longer than T2** (T1 ~300-2000 ms, T2 ~30-150 ms). Water and
  most pathology (high water content): **long T1, long T2**. Fat: **short T1, short T2**.
- **Spin echo refocusing:** because T2\* decay from field inhomogeneity is fast, a **180 degree pulse**
  (Hahn) reverses the precession so faster and slower spins refocus into an echo; the echo occurs at the
  echo time **TE**, so the 180 must be applied at **TE/2**. This recovers the inhomogeneity-related
  dephasing (T2\*) and leaves true T2.

## Content to add

1. **Lesson 1 — "Making an MR signal: protons, B0, Larmor, and resonance"** —
   `{topic:"instrumentation", kind:"education"}`, all six body fields. Hydrogen proton as a tiny magnet;
   parallel/anti-parallel and the NMV along B0; precession and the Larmor equation fo = gamma x B0 with
   gamma = 42.58 MHz/T; RF/B1 perpendicular at the Larmor frequency, energy transfer by resonance;
   transverse magnetization induces the coil signal. exam_traps: gamma for hydrogen is 42.58 MHz/T so
   Larmor frequency scales with field (63.9 MHz at 1.5T, 127.7 MHz at 3T); B1 must be perpendicular to B0
   and near the Larmor frequency or no resonance.
2. **Lesson 2 — "Relaxation: T1 spin-lattice and T2 spin-spin"** —
   `{topic:"contrast-weighting", kind:"education"}`, all six body fields. T1 longitudinal recovery =
   energy to the lattice, efficiency depends on molecular motion vs Larmor frequency (free water long T1,
   fat short T1); T1 = 63% recovery. T2 transverse decay = spin-spin dephasing; T2 = 37% remaining. T1
   always longer than T2; water long/long, fat short/short. exam_traps: T1 is 63% recovered (not
   complete) and T2 is 37% remaining (not zero); T1 is always longer than T2 for a given tissue; free
   water has a LONG T1 because its fast small molecules transfer energy poorly.
3. **Lesson 3 — "Dephasing, T2 vs T2\*, and the spin-echo refocusing pulse"** —
   `{topic:"pulse-sequences", kind:"education"}`, all six body fields. Two sources of transverse
   dephasing: true spin-spin interactions (T2) and external field inhomogeneity (adds to give faster
   T2\*); a 180 degree refocusing pulse reverses precession so spins rephase into an echo at TE, so the
   180 is placed at TE/2; this recovers the inhomogeneity dephasing that gradient echo cannot. exam_traps:
   T2\* is faster than (shorter than) T2 because it adds field inhomogeneity; the refocusing pulse is 180
   degrees and sits at TE/2; spin echo recovers T2\* losses, gradient echo does not.
4. **~24 quiz items** split 8 `instrumentation` (hydrogen is the imaged nucleus; NMV forms along B0;
   Larmor equation and gamma = 42.58 MHz/T; Larmor frequency at 1.5T vs 3T; B1 perpendicular and near
   Larmor; resonance is the energy-transfer condition; transverse magnetization induces the signal;
   parallel vs anti-parallel energy) + 8 `contrast-weighting` (T1 = spin-lattice / longitudinal, T2 =
   spin-spin / transverse; T1 63% recovery; T2 37% remaining; T1 longer than T2; water long/long, fat
   short/short; why free water has long T1; pathology tends to long T2) + 8 `pulse-sequences` (dephasing
   causes; T2 vs T2\* which is shorter; what T2\* adds; 180 degree refocusing pulse; 180 sits at TE/2;
   spin echo recovers inhomogeneity losses; gradient echo does not refocus). Four balanced-length
   options, no em dashes, no AI tells. No prompt may duplicate an existing bank question.

Voice per [[feedback_no_ai_tells_content]].

## Integration, testing, edge cases

Same pipeline as phases 2-4: Fable author writes `{lessons:[3], quiz:[~24]}` -> Fable accuracy review
(physics-correct, distinct from existing parameter-level content, plausible distractors, balanced
lengths, no dashes) -> controller appends to `data/course_content.json` (fresh ords after global max,
byte-stable `quiz_length_tools.dump`) -> bump `tests/test_course_depth.py` count 33 -> 36 -> guard +
depth + images tests green + `ruff check src/ tests/` -> idempotent MCP reseed by `body->>'title'`/
`prompt`. No JS/engine change. Branch off fresh main after #399 (phase-4 parameters) merges so the
baseline is 428 items / depth 33. Edge cases: answer-length tell (guard), duplicate prompt/title (applier
+ reseed not-exists guard), overlap with existing T1/T2 content (accuracy reviewer + author instruction),
depth-count drift (bump the two `33`s to `36`).

## Out of scope

- Any `course.js` / curriculum-map change (all three topics already mapped).
- Image-based questions (text only here).
- Re-teaching the parameter-level TR/TE weighting table (covered by phase 4 `contrast-weighting`).
- The "MR Basic Physics 2nd class" deck (23pp, poor text extraction) — that is a separate candidate
  phase 6.
