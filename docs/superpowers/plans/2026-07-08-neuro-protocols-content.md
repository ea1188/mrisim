# Neuro Clinical-Protocol Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two reading lessons plus ~18 board-style quiz items on neuro MRI clinical protocols to the paid course, appended to the existing `procedures-anatomy` and `procedures-protocols` topics in `data/course_content.json`, and reseeded to Supabase.

**Architecture:** This is content authoring, not code. Fable subagents author the JSON bodies from the generalized source facts in the spec; the controller appends them to the single source file `data/course_content.json` via the byte-stable `scripts/quiz_length_tools.py` helpers, verifies with the existing pytest guards, and reseeds Supabase idempotently over MCP. No JS/engine code changes; no `course.js` change (both topics are already mapped in `TOPIC_CFG`).

**Tech Stack:** Python 3 (`python3`), pytest, ruff, `scripts/quiz_length_tools.py` (`load`/`dump`/`flagged_items`/`is_text_quiz`), Supabase MCP `execute_sql`.

## Global Constraints

- Every clinical claim must be ACR-consistent / defensible against current general MRI practice, not merely the deck.
- Full generalization: NO surviving NYU/site/brand specifics — replace `Vueway`→"weight-based gadolinium contrast", `EPIC`→"the dose calculator / department protocol", `GRASP`→"a dynamic contrast-enhanced (DCE) sequence", `BrainLab`→"stereotactic / neuronavigation planning"; drop phone numbers, floor/site names, PACS workflow, "greaseboard".
- Voice: natural clinical prose. NO AI-tell punctuation. NO em dashes or en dashes (`—`/`–`) anywhere in any body field.
- Every quiz item: exactly 4 options, keyed answer at index 0, balanced option lengths so the keyed answer does not exceed every distractor by >20% (the `tests/test_quiz_length.py` guard must stay green).
- Every education body carries all six fields: `title`, `html`, `keypoints` (~5), `worked_example` (non-empty str), `memory_hooks` (1-3 str), `exam_traps` (1-3 str).
- Prompts and lesson titles must be unique across the entire existing bank.
- `data/course_content.json` is the single source; write it only via `quiz_length_tools.dump` (byte-stable: `json.dumps(d, indent=2, ensure_ascii=False)+"\n"`) so the diff is only the additions.

---

### Task 1: Author neuro content patch (2 lessons + ~18 quiz)

**Files:**
- Create: `patches/neuro_protocols.json` (git-ignored scratch; the authored patch)

**Interfaces:**
- Produces: a JSON file of shape
  `{ "lessons": [ {"topic","body"}, {"topic","body"} ], "quiz": [ {"topic","body"}, ... ] }`
  where lesson 1 `topic` is `"procedures-anatomy"`, lesson 2 `topic` is `"procedures-protocols"`, each
  quiz entry carries its own `topic` (either of those two), and every `body` matches the schema in
  Global Constraints. Consumed by Task 3 (apply).

- [ ] **Step 1: Author lesson 1** — `topic:"procedures-anatomy"`, title exactly
  `"Brain MRI: routine protocol and when to enhance"`. Cover (generalized): head coil; skull-base-to-vertex
  coverage; AC-PC line axial angulation; the diffusion(high-b vs ADC)→acute stroke / SWI→hemorrhage-microbleed
  / FLAIR(CSF-nulled)→MS triad and what each demonstrates; 3D sagittal reformats; weight-based gadolinium
  enhancement and structures that normally enhance (pituitary, choroid plexus, vessels, nasal mucosa);
  routine vs tumor/pre-op/post-op/mets/demyelinating indications. All six body fields; exam_traps include
  "FLAIR nulls CSF (dark) vs T2 (bright)" and "high-b bright alone is not diffusion restriction without a
  dark ADC".

- [ ] **Step 2: Author lesson 2** — `topic:"procedures-protocols"`, title exactly
  `"Specialized neuro studies: pituitary, IAC, and stereotactic planning"`. Cover (generalized): dynamic
  pituitary (micro <10 mm vs macro >=10 mm; microadenomas need dynamic/delayed post-contrast because they
  enhance later than normal gland; posterior lobe T1-bright; gland in sella turcica; full-dose contrast);
  IAC (cranial nerves VII facial and VIII vestibulocochlear; indications acoustic neuroma / vestibular
  schwannoma, sensorineural hearing loss, vertigo, tinnitus; thin-section heavily-T2 CISS-type cisternal
  technique; trigeminal/facial-nerve Bell's-palsy variant); stereotactic / neuronavigation planning (head
  straight, do NOT angle the slice package, keep full coverage, do not clip nose/ears/occiput, for accurate
  registration). All six body fields.

- [ ] **Step 3: Author ~9 `procedures-anatomy` quiz items** covering: head coil; skull-base-to-vertex
  coverage; AC-PC axial angulation; diffusion→acute stroke (high-b vs ADC direction); SWI→hemorrhage/
  microbleed; FLAIR nulls CSF / demonstrates MS; 3D sagittal reformats; weight-based enhancement dosing;
  which structures normally enhance. Each `{prompt, options[4], answer:0, explain}`, options balanced-length.

- [ ] **Step 4: Author ~9 `procedures-protocols` quiz items** covering: micro vs macroadenoma 10 mm
  threshold; why dynamic/delayed imaging finds microadenomas; posterior pituitary T1-bright / sella turcica;
  IAC images CN VII & VIII; acoustic neuroma / hearing-loss indication; thin-section CISS-type cisternal
  technique; stereotactic no-angulation rule; stereotactic full-coverage (don't clip) rule;
  trigeminal/facial-nerve variant. Each `{prompt, options[4], answer:0, explain}`, options balanced-length.

- [ ] **Step 5: Write the patch file** to `patches/neuro_protocols.json` as valid UTF-8 JSON with the
  shape in Interfaces. Verify it parses: `python3 -c "import json;d=json.load(open('patches/neuro_protocols.json'));print(len(d['lessons']),len(d['quiz']))"` → expect `2 <n>` with n around 18.

### Task 2: Accuracy review the patch

**Files:**
- Read: `patches/neuro_protocols.json`

- [ ] **Step 1: Review** every lesson and quiz item for: medical correctness (ACR-consistent), full
  generalization (grep the file for `Vueway|EPIC|GRASP|BrainLab|NYU` and any phone/floor/site specific —
  expect zero), distractors wrong-but-plausible, keyed answer correct at index 0, balanced option lengths,
  no em/en dashes, unique prompts/titles. Fix any finding in place in the patch file.

- [ ] **Step 2: Verify no dashes and no brand terms**
  Run: `python3 -c "import json,re;d=json.load(open('patches/neuro_protocols.json'));s=json.dumps(d);bad=[t for t in ['Vueway','EPIC','GRASP','BrainLab','NYU'] if t in s];print('DASH' if re.search(r'[—–]',s) else 'no-dash', 'BRANDS:',bad)"`
  Expected: `no-dash BRANDS: []`

### Task 3: Apply patch to course_content.json

**Files:**
- Modify: `data/course_content.json` (append items)
- Create: `$CLAUDE_JOB_DIR/tmp/apply_neuro.py` (one-off applier script)

**Interfaces:**
- Consumes: `patches/neuro_protocols.json` from Task 1.

- [ ] **Step 1: Write the applier** at `$CLAUDE_JOB_DIR/tmp/apply_neuro.py`:

```python
import json, importlib.util
spec = importlib.util.spec_from_file_location("qlt", "scripts/quiz_length_tools.py")
qlt = importlib.util.module_from_spec(spec); spec.loader.exec_module(qlt)
doc = qlt.load()
patch = json.load(open("patches/neuro_protocols.json"))
items = doc["items"]
titles = {it["body"].get("title") for it in items if it.get("kind") == "education"}
prompts = {it["body"].get("prompt") for it in items if it.get("kind") == "quiz"}
ord_next = max(it["ord"] for it in items) + 1
added = 0
for les in patch["lessons"]:
    assert les["body"]["title"] not in titles, "dup title " + les["body"]["title"]
    items.append({"topic": les["topic"], "kind": "education", "ord": ord_next, "body": les["body"]})
    ord_next += 1; added += 1
for q in patch["quiz"]:
    assert q["body"]["prompt"] not in prompts, "dup prompt"
    assert len(q["body"]["options"]) == 4, "need 4 options"
    items.append({"topic": q["topic"], "kind": "quiz", "ord": ord_next, "body": q["body"]})
    ord_next += 1; added += 1
qlt.dump(doc)
print("appended", added, "items; total", len(items))
```

- [ ] **Step 2: Run it**
  Run: `python3 "$CLAUDE_JOB_DIR/tmp/apply_neuro.py"`
  Expected: `appended 20 items; total 294` (counts approximate; 2 lessons + ~18 quiz on top of 274).

- [ ] **Step 3: Bump the education-module count** in `tests/test_course_depth.py`: change the two
  occurrences of `17` (the assert `len(bodies) == 17` and the module docstring "All 17 premium education
  modules") to `19`.

### Task 4: Verify (guards + suite + lint)

- [ ] **Step 1: Answer-length guard + depth + images**
  Run: `python3 -m pytest tests/test_quiz_length.py tests/test_course_depth.py tests/test_course_images.py -q`
  Expected: all pass. If `test_no_answer_length_tell` fails, an authored quiz has an over-long key — fix that
  item's option lengths in `patches/neuro_protocols.json`, `git checkout data/course_content.json` (the
  applier is not idempotent), then re-run Task 3.

- [ ] **Step 2: Lint**
  Run: `ruff check src/ tests/`
  Expected: no errors.

- [ ] **Step 3: Commit**
  Run:
```bash
git add data/course_content.json tests/test_course_depth.py
git commit -m "content(course): neuro clinical protocols (PDF phase 2, region 1)"
```

### Task 5: Reseed Supabase + open PR

**Files:** none (DB + PR)

- [ ] **Step 1: Reseed** the new rows into Supabase `course_content` (project ref `idgyjmamxxyddjuaamit`,
  course `mri-core`) via MCP `execute_sql`, idempotent INSERT guarded by a not-exists check on
  `body->>'title'` (lessons) and `body->>'prompt'` (quiz). Build the INSERT statements from the appended
  items (topic, kind, ord, body::jsonb).

- [ ] **Step 2: Verify DB** with `execute_sql`:
  `select topic, kind, count(*) from course_content where course='mri-core' and topic in ('procedures-anatomy','procedures-protocols') group by 1,2 order by 1,2;`
  Expected: procedures-anatomy education 2 + quiz ~20; procedures-protocols education 2 + quiz ~23.

- [ ] **Step 3: Push + PR**
  Run:
```bash
git push -u origin feat/course-neuro-protocols
gh pr create --title "content(course): neuro clinical protocols (PDF phase 2, region 1)" --body "..."
```

## Self-Review

- **Spec coverage:** Lesson 1 (Task 1 S1), Lesson 2 (Task 1 S2), ~18 quiz split 9/9 (Task 1 S3-4),
  generalization (Global Constraints + Task 2), guard/depth/images tests (Task 4), reseed (Task 5). All
  spec sections mapped.
- **Placeholder scan:** none — commands and code are concrete.
- **Type consistency:** patch shape `{lessons:[{topic,body}], quiz:[{topic,body}]}` is produced in Task 1
  and consumed verbatim by the Task 3 applier; item schema matches `{topic,kind,ord,body}` throughout.
