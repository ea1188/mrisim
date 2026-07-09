# Premium Quiz Rebalance — Batch 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 21 ARRT-outline-anchored premium quiz questions (three-d-recon +8, fat-suppression +6, flow-artifacts +7) to grow Image Production toward its 53% exam weighting.

**Architecture:** Content-authoring, not code. Each topic is one task: author its questions against named ARRT outline subtopics that are not already covered, append them to `data/course_content.json` via the byte-stable dump helper, and verify the answer-length guard stays green. A final task runs the full guard suite and verifies the counts. The Supabase reseed and the user accuracy-review are controller-gated steps after the plan's tasks, not subagent work.

**Tech Stack:** `data/course_content.json` (source), `scripts/quiz_length_tools.py` (`load`/`dump`/`flagged_items`), pytest guards, Python 3.11 for the full suite.

## Global Constraints

- Content accuracy is paramount (paid ARRT registry-prep product). Every question is anchored to a named ARRT MRI content-outline subtopic and must be factually correct.
- Do not duplicate an existing question in the same topic. Each task lists the existing prompts to avoid and the uncovered anchors to write toward.
- No AI-tell punctuation, no em dashes; natural clinical prose.
- Answer-length guard must stay green: the keyed answer must not exceed 1.2x the length of every distractor (`scripts/quiz_length_tools.py` `flagged_items`). No new flagged items.
- Item shape: `{"topic": <id>, "kind": "quiz", "ord": <fresh>, "body": {"prompt", "options": [4], "answer": 0, "explain"}}`. Author the correct option at index 0 with `answer: 0` (matches existing items; `course.js` shuffles at render).
- Use a fresh contiguous ord block starting at 1140 (max ord in use is 1131).
- Append/dump only via `scripts/quiz_length_tools.py` `load()` / `dump()` (indent 2, `ensure_ascii=False`, trailing newline) to keep the file byte-stable.
- User approves the drafted questions for clinical/physics accuracy before any Supabase reseed. Reseed after approval; a commit alone does not ship.
- No `Co-Authored-By: Claude` trailers on commits.
- Run `ruff check src/ tests/` and the web/pytest guards before merge.

**Authoring quality bar (applies to every question in Tasks 1-3):**
- Registry difficulty: tests a real concept, not trivia. Four options, exactly one correct.
- Distractors are plausible and specifically wrong (a real misconception a tech might hold), never absurd.
- Keep the correct option similar in length to the distractors (balance by padding distractors with plausible-but-false detail, never by trimming the key).
- `explain` states why the key is right and, where useful, why a tempting distractor is wrong. No em dashes.

---

### Task 1: three-d-recon (+8 questions)

**Files:**
- Modify: `data/course_content.json` (append 8 quiz items with `topic: "three-d-recon"`)

**Interfaces:**
- Consumes: nothing.
- Produces: 8 new `three-d-recon` quiz items (ords 1140-1147), bringing the topic from 8 to 16.

**Existing prompts to NOT duplicate:** 3D advantage over 2D; MIP display; isotropic voxels; MinIP display; 3D GRE vs 2D; MPR requirement; partial-volume averaging; cross-talk reduction.

**Uncovered ARRT anchors to write toward (pick 8):** slice-direction aliasing / slab wrap and its control (slice oversampling); scan-time cost of 3D (second phase-encode axis = more encodings); why 3D partitions are contiguous with no slice gap; SNR source of 3D (whole-slab excitation, SNR scales with sqrt of partitions); balanced SSFP / volumetric steady-state use; subtraction postprocessing (pre/post-contrast MRA); anisotropic vs isotropic reformat quality (thick-slice 2D reformats blur); k-space has two phase-encode directions in 3D.

- [ ] **Step 1: Read the existing three-d-recon items** so new questions do not overlap.

Run: `python3 -c "import json; d=json.load(open('data/course_content.json')); [print(x['body']['prompt']) for x in d['items'] if x.get('topic')=='three-d-recon' and x.get('kind')=='quiz']"`

- [ ] **Step 2: Author the 8 questions.** Use this exact format (worked example — do not reuse this one, it covers slice oversampling; write 8 fresh ones across the uncovered anchors):

```json
{
  "topic": "three-d-recon",
  "kind": "quiz",
  "ord": 1140,
  "body": {
    "prompt": "In a 3D volumetric acquisition, wrap-around along the slice-select (partition) direction is prevented by:",
    "options": [
      "Oversampling in the slice-encode direction so tissue outside the slab does not alias into it",
      "Lowering the receive bandwidth to widen the sampled frequency range at each partition",
      "Shortening the echo time so that fewer partitions are needed to fill the slab",
      "Increasing the flip angle to saturate signal from tissue beyond the edges of the slab"
    ],
    "answer": 0,
    "explain": "A 3D acquisition phase-encodes the slice direction, so anatomy beyond the excited slab can fold back onto the end partitions. Slice-direction oversampling extends sampling past the slab edges and discards the extra partitions, removing the wrap. Bandwidth, TE, and flip angle do not address slice-direction aliasing."
  }
}
```

- [ ] **Step 3: Append the 8 items via the byte-stable helper.** Write a throwaway script under `$CLAUDE_JOB_DIR/tmp` that loads, extends, and dumps:

```python
import sys; sys.path.insert(0, "scripts")
import quiz_length_tools as q
doc = q.load()
new = [ ... the 8 dict items, ords 1140-1147 ... ]
doc["items"].extend(new)
q.dump(doc)
```

Run it with `python3`.

- [ ] **Step 4: Verify the answer-length guard flags none of the new items.**

Run: `python3 -c "import sys; sys.path.insert(0,'scripts'); import quiz_length_tools as q; d=q.load(); new=[x for x in d['items'] if x.get('topic')=='three-d-recon' and x.get('ord',0)>=1140]; print('new:',len(new),'flagged:',len(q.flagged_items(new)))"`
Expected: `new: 8 flagged: 0`

- [ ] **Step 5: Verify count and JSON validity.**

Run: `python3 -c "import json; d=json.load(open('data/course_content.json')); print('three-d-recon:', sum(1 for x in d['items'] if x.get('topic')=='three-d-recon' and x.get('kind')=='quiz'))"`
Expected: `three-d-recon: 16`

- [ ] **Step 6: Commit.**

```bash
git add data/course_content.json
git commit -m "content(quiz): +8 three-d-recon questions (ARRT Image Production, Batch 1)"
```

---

### Task 2: fat-suppression (+6 questions)

**Files:**
- Modify: `data/course_content.json` (append 6 quiz items with `topic: "fat-suppression"`)

**Interfaces:**
- Consumes: nothing (independent of Task 1; uses ords 1148-1153).
- Produces: 6 new `fat-suppression` items, bringing the topic from 10 to 16.

**Existing prompts to NOT duplicate:** spectral mechanism; when spectral fails; STIR mechanism; STIR+gadolinium; Dixon separation; water excitation; 1.5T vs 3T spectral; reason to suppress fat; T1 SE without fat-sat appearance; T1 SE with fat-sat appearance.

**Uncovered ARRT anchors to write toward (pick 6):** STIR TI selection (TI set near the fat null, roughly 150-170 ms at 1.5T; TI ~ 0.69 x T1fat); STIR is not tissue-specific (it nulls anything with a T1 near fat's, so enhancing tissue or methemoglobin can be suppressed); Dixon advantage over spectral sat (tolerant of B0 inhomogeneity, yields water/fat/in/out images); the fat-water chemical-shift frequency separation (about 3.5 ppm, roughly 220 Hz at 1.5T and 440 Hz at 3T); in-phase / out-of-phase TE timing (about 4.4 ms in-phase, 2.2 ms out-of-phase at 1.5T); SPAIR / adiabatic spectral inversion (B1-insensitive spectral suppression); why fat stays bright on fast spin echo (J-coupling).

- [ ] **Step 1: Read the existing fat-suppression items.**

Run: `python3 -c "import json; d=json.load(open('data/course_content.json')); [print(x['body']['prompt']) for x in d['items'] if x.get('topic')=='fat-suppression' and x.get('kind')=='quiz']"`

- [ ] **Step 2: Author the 6 questions.** Format worked example (covers STIR TI value; write 6 fresh across the uncovered anchors, not this one):

```json
{
  "topic": "fat-suppression",
  "kind": "quiz",
  "ord": 1148,
  "body": {
    "prompt": "On a STIR sequence at 1.5 T, fat is nulled by setting the inversion time (TI) to approximately:",
    "options": [
      "150 to 170 ms, the point where recovering fat magnetization crosses zero",
      "About 500 ms, matching the null point of free water at that field strength",
      "The same value as the echo time so the two coincide during readout",
      "Roughly 2500 ms, near the repetition time used for the sequence"
    ],
    "answer": 0,
    "explain": "STIR nulls fat by choosing a TI near 0.69 times the T1 of fat, which is about 150 to 170 ms at 1.5 T, so the inverted fat magnetization is passing through zero at excitation. Water has a much longer T1 and is not nulled at that TI, and TI is independent of TE and TR."
  }
}
```

- [ ] **Step 3: Append the 6 items** via the same load/extend/dump helper (ords 1148-1153).

- [ ] **Step 4: Verify the guard flags none.**

Run: `python3 -c "import sys; sys.path.insert(0,'scripts'); import quiz_length_tools as q; d=q.load(); new=[x for x in d['items'] if x.get('topic')=='fat-suppression' and x.get('ord',0)>=1148]; print('new:',len(new),'flagged:',len(q.flagged_items(new)))"`
Expected: `new: 6 flagged: 0`

- [ ] **Step 5: Verify count.**

Run: `python3 -c "import json; d=json.load(open('data/course_content.json')); print('fat-suppression:', sum(1 for x in d['items'] if x.get('topic')=='fat-suppression' and x.get('kind')=='quiz'))"`
Expected: `fat-suppression: 16`

- [ ] **Step 6: Commit.**

```bash
git add data/course_content.json
git commit -m "content(quiz): +6 fat-suppression questions (ARRT Image Production, Batch 1)"
```

---

### Task 3: flow-artifacts (+7 questions)

**Files:**
- Modify: `data/course_content.json` (append 7 quiz items with `topic: "flow-artifacts"`)

**Interfaces:**
- Consumes: nothing (independent; uses ords 1154-1160).
- Produces: 7 new `flow-artifacts` items, bringing the topic from 21 to 28.

**Existing prompts to NOT duplicate (this topic is already broad):** ghosting direction; VENC below peak; TOF bright blood; chemical-shift misregistration; Gibbs ripple; wrap-around correction; India-ink opposed-phase; metal susceptibility void; sat-band purpose; magic angle; gating purpose; chemical shift second kind; dielectric; flow void on SE; entry-slice / flow-related enhancement; cross-excitation; truncation worst-case; shifting pulsation ghosts by swapping phase/frequency; TOF image; ghost-band image; SWI blooming.

**Uncovered ARRT anchors to write toward (pick 7):** gradient moment nulling / flow compensation (added gradient lobes rephase moving spins to reduce flow artifact and brighten slow flow); even-echo rephasing; spatial pre-saturation placement (a sat band superior to the slab suppresses inflowing venous signal, inferior suppresses arterial); increasing NSA / signal averaging reduces the intensity of pulsation ghosts; respiratory compensation options (bellows/ordered phase encoding, navigator echo, breath-hold) distinct from cardiac gating; pseudogating (a TR that happens to match the cardiac cycle); ghost spacing / number relates to the number of phase-encode steps and the pulsation period.

- [ ] **Step 1: Read the existing flow-artifacts items.**

Run: `python3 -c "import json; d=json.load(open('data/course_content.json')); [print(x['body']['prompt']) for x in d['items'] if x.get('topic')=='flow-artifacts' and x.get('kind')=='quiz']"`

- [ ] **Step 2: Author the 7 questions.** Format worked example (covers flow compensation; write 7 fresh across the uncovered anchors, not this one):

```json
{
  "topic": "flow-artifacts",
  "kind": "quiz",
  "ord": 1154,
  "body": {
    "prompt": "Gradient moment nulling (flow compensation) reduces flow artifact primarily by:",
    "options": [
      "Adding gradient lobes that rephase spins moving at constant velocity so they are not left dephased at echo time",
      "Placing a saturation band across the vessel to remove all inflowing signal before readout",
      "Matching the repetition time to the cardiac cycle so pulsation repeats identically each view",
      "Lowering the flip angle so that fast-moving spins contribute little transverse signal"
    ],
    "answer": 0,
    "explain": "Flow compensation adds balanced gradient lobes whose net first moment is zero for constant-velocity spins, so moving protons are rephased at the echo rather than left with a position-dependent phase. This reduces flow ghosting and can brighten slow flow. Saturation bands, gating, and flip angle work by different mechanisms."
  }
}
```

- [ ] **Step 3: Append the 7 items** via the load/extend/dump helper (ords 1154-1160).

- [ ] **Step 4: Verify the guard flags none.**

Run: `python3 -c "import sys; sys.path.insert(0,'scripts'); import quiz_length_tools as q; d=q.load(); new=[x for x in d['items'] if x.get('topic')=='flow-artifacts' and x.get('ord',0)>=1154]; print('new:',len(new),'flagged:',len(q.flagged_items(new)))"`
Expected: `new: 7 flagged: 0`

- [ ] **Step 5: Verify count.**

Run: `python3 -c "import json; d=json.load(open('data/course_content.json')); print('flow-artifacts:', sum(1 for x in d['items'] if x.get('topic')=='flow-artifacts' and x.get('kind')=='quiz'))"`
Expected: `flow-artifacts: 28`

- [ ] **Step 6: Commit.**

```bash
git add data/course_content.json
git commit -m "content(quiz): +7 flow-artifacts questions (ARRT Image Production, Batch 1)"
```

---

### Task 4: Full guard suite + batch verification

**Files:**
- No new files. Runs the repo's content guards over the full pool.

**Interfaces:**
- Consumes: the 21 items added in Tasks 1-3.
- Produces: a green guard run over the whole `data/course_content.json`.

- [ ] **Step 1: Run the full quiz-length guard over the whole pool.**

Run: `python3.11 -m pytest tests/test_quiz_length.py -q`
Expected: PASS (no newly flagged items).

- [ ] **Step 2: Run the depth and image guards.**

Run: `python3.11 -m pytest tests/test_course_depth.py tests/test_course_images.py -q`
Expected: PASS.

- [ ] **Step 3: Verify the three Batch-1 floors in one command.**

Run:
```bash
python3 -c "import json,collections; d=json.load(open('data/course_content.json')); c=collections.Counter(x['topic'] for x in d['items'] if x.get('kind')=='quiz'); print({k:c[k] for k in ['three-d-recon','fat-suppression','flow-artifacts']})"
```
Expected: `{'three-d-recon': 16, 'fat-suppression': 16, 'flow-artifacts': 28}`

(No brittle count *test* is committed: a hardcoded floor assertion would need editing every batch. The floors are verified here as a command instead.)

- [ ] **Step 4: Confirm no accidental byte churn.** The diff should be pure additions (21 new item objects), no reordering of existing items.

Run: `git diff --stat main..HEAD -- data/course_content.json`
Expected: only insertions.

- [ ] **Step 5 (controller-gated, NOT a subagent step): user accuracy review + Supabase reseed.**

After the user approves the 21 drafted questions for clinical/physics accuracy, reseed the Supabase `course_content` table (course `mri-core`) so the live course serves them. Until then the questions are committed but not shipped. This step is performed by the controller, not an implementer subagent.

---

## Self-Review

**1. Spec coverage:**
- Grow three-d-recon 8->16, fat-suppression 10->16, flow-artifacts 21->28 (+21 total) -> Tasks 1, 2, 3. Covered.
- ARRT-outline anchors, no duplication -> each task lists existing prompts to avoid + uncovered anchors. Covered.
- Item shape, answer at index 0, fresh ord block 1140+ -> Global Constraints + each task's ords. Covered.
- Byte-stable append via quiz_length_tools load/dump -> Step 3 of each authoring task. Covered.
- Answer-length guard stays green -> Step 4 of each task + Task 4 Step 1. Covered.
- Depth guard -> Task 4 Step 2. Covered.
- Count verification (16/16/28) -> per-task Step 5 + Task 4 Step 3. Covered (as a command, not a committed brittle test — noted deviation).
- User approval before reseed; reseed after -> Task 4 Step 5, controller-gated. Covered.
- No AI tells / accuracy bar -> Global Constraints + authoring quality bar. Covered.

**2. Placeholder scan:** The `[ ... the 8 dict items ... ]` in the append steps is intentional — the 21 questions are the authoring deliverable and cannot be pre-written in the plan without doing the authoring. Each task instead gives the exact item format, one full worked example, the uncovered-anchor list, and the exact verify commands. No other placeholders.

**3. Type consistency:** Item schema (`topic`/`kind`/`ord`/`body.{prompt,options,answer,explain}`) is identical across all tasks and matches the existing file. Ord blocks are contiguous and non-overlapping: 1140-1147 (T1), 1148-1153 (T2), 1154-1160 (T3). Topic ids match the file exactly.
