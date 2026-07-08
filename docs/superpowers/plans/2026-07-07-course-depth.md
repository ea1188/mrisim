# Course Module Depth (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each of the 16 premium education modules a worked example, memory hooks, and common-exam-trap notes, rendered on the course "Course material" cards.

**Architecture:** Add three optional fields to each education `body` in `data/course_content.json` (the source that `scripts/seed_course_content.py` re-seeds into Supabase — the `body` column is jsonb, so no schema migration). Render them in `web/course.js` `renderTopic` with CSS in `web/course.html`. A pytest data check enforces the schema and the no-em-dash rule.

**Tech Stack:** JSON data + Python (edit/validate), vanilla ES5 browser JS + CSS (render), pytest (validation, runs in the existing CI `test` job).

## Global Constraints

- **`data/course_content.json` is the SOURCE**, re-seeded to Supabase by the owner via `scripts/seed_course_content.py` (needs the service_role key). **Do NOT run the seed** in any task — the plan produces the JSON + render code only.
- **Edit the JSON by load → mutate → dump** with `json.dumps(d, indent=2, ensure_ascii=False) + "\n"` (verified byte-identical to the current file, so diffs stay minimal). Never hand-edit the raw JSON braces.
- **Only touch the target education bodies.** Do not alter existing `title`/`html`/`keypoints`, other `body` fields, quiz/reference items, `_note`, or `course`.
- **No em dashes (—) or en dashes (–) and no AI-tell punctuation** in any added field. Natural prose. (Extends the project's no-AI-tells content rule.)
- **Accuracy is the primary bar.** Every field is factually correct MRI content for the module's topic; audience = ARRT registry candidates + new MRI technologists. Concrete and exam-relevant, not padded.
- **Per-module quantity:** exactly 1 `worked_example` (an HTML string), 2–3 `memory_hooks` (plain strings), 2–3 `exam_traps` (plain strings).
- `web/course.js` is ES5-style: `var`, function expressions, the `h(tag, attrs, kids)` builder. Use `text:` for plain strings; `html:` only for the trusted `worked_example` HTML (same as the existing `body.html`).
- Display name "MRISim"; professional/clinical tone (no emoji, gradients, pills).
- No `Co-Authored-By: Claude` trailer on commits.
- `course.js`/`course.html` are network-first SHELL files → no service-worker cache bump.

## Data model (added to each education `body`)

```json
{
  "title": "…", "html": "…", "keypoints": ["…"],
  "worked_example": "<p>one short HTML scenario that walks the reasoning to an answer</p>",
  "memory_hooks": ["a correct, memorable device", "…"],
  "exam_traps": ["a real registry-level confusion, e.g. don't confuse X with Y", "…"]
}
```

## Quality exemplar (module "Flip angle: the Ernst angle and the SAR trade-off")

Every content batch must match this bar. This exemplar is authored here; the Batch A task uses it verbatim for that module and writes the same quality for its other three.

```json
{
  "worked_example": "<p>You are running a T1-weighted spoiled gradient echo of the brain with a short TR of 8 ms. At a 90 degree flip the longitudinal magnetization barely recovers between pulses, so the signal is weak. Lowering the flip toward the Ernst angle for white matter, roughly 12 to 15 degrees at that TR, restores signal. The Ernst angle is the flip that maximizes steady-state signal for a given TR and T1, where cos(Ernst) equals exp(-TR/T1). A short TR pushes the Ernst angle small, which is why fast gradient echo uses low flip angles.</p>",
  "memory_hooks": [
    "Short TR wants a small flip. As TR drops, the Ernst angle drops with it.",
    "cos of the Ernst angle equals E1, and E1 is exp(-TR over T1)."
  ],
  "exam_traps": [
    "SAR scales with the square of the flip angle and with the square of field strength, so trimming the flip angle is the fastest way to cut SAR.",
    "The Ernst angle maximizes signal, not contrast. A higher flip can give stronger T1 weighting even though total signal is lower."
  ]
}
```

## Batches (16 modules, matched by exact `body.title`)

- **Batch A — physics core** (Task 2): "Pulse sequences: SE, FSE, GRE, EPI and how they are built", "Data acquisition: k-space, encoding and the Fourier transform", "MRI instrumentation: magnet, gradients, RF and coils", "Flip angle: the Ernst angle and the SAR trade-off".
- **Batch B — contrast & image quality** (Task 3): "Contrast & weighting: the exam synthesis", "Image quality: SNR, CNR, resolution & the trade-offs", "Fat suppression: STIR, spectral, Dixon and water excitation", "MRI contrast agents: gadolinium, safety and special agents".
- **Batch C — reading & protocols** (Task 4): "Reading pathology: where lesions hide and what lights them up", "Regional anatomy: planes and sequences by body part", "Building a protocol: why each sequence is there", "3D imaging and reconstruction: volumes, MIP and reformats".
- **Batch D — flow, safety & care** (Task 5): "Flow, function and artifacts: MRA methods and the artifacts to name", "MR angiography and venography: TOF, PC and contrast methods", "MR safety: the exam-focused overview", "Patient care: screening to monitoring".

---

## Task 1: Render the depth blocks

**Files:**
- Modify: `web/course.js` (education card loop in `renderTopic`)
- Modify: `web/course.html` (CSS)

**Interfaces:**
- Consumes: education `body` objects that may carry `worked_example` (string), `memory_hooks` (array), `exam_traps` (array).
- Produces: rendered `.edu-worked` / `.edu-hooks` / `.edu-traps` blocks inside each `.edu` card, shown only when the field is present.

- [ ] **Step 1: Insert the three render blocks**

In `web/course.js`, in the education card loop of `renderTopic`, find:

```js
        if (b.keypoints && b.keypoints.length) {
          var kp = h("div", { class: "keypoints" }, [h("b", { text: "Key points" })]);
          var ul = h("ul");
          b.keypoints.forEach(function (p) { ul.appendChild(h("li", { text: p })); });
          kp.appendChild(ul); card.appendChild(kp);
        }
        var foot = h("div", { class: "edu-foot" });
```

and replace it with (adds the three blocks between Key points and the footer):

```js
        if (b.keypoints && b.keypoints.length) {
          var kp = h("div", { class: "keypoints" }, [h("b", { text: "Key points" })]);
          var ul = h("ul");
          b.keypoints.forEach(function (p) { ul.appendChild(h("li", { text: p })); });
          kp.appendChild(ul); card.appendChild(kp);
        }
        if (b.worked_example) {
          card.appendChild(h("div", { class: "edu-worked" }, [
            h("h5", { text: "Worked example" }),
            h("div", { class: "body", html: b.worked_example }),
          ]));
        }
        if (b.memory_hooks && b.memory_hooks.length) {
          var hk = h("div", { class: "edu-hooks" }, [h("h5", { text: "Memory hooks" })]);
          var hul = h("ul");
          b.memory_hooks.forEach(function (p) { hul.appendChild(h("li", { text: p })); });
          hk.appendChild(hul); card.appendChild(hk);
        }
        if (b.exam_traps && b.exam_traps.length) {
          var tp = h("div", { class: "edu-traps" }, [h("h5", { text: "Exam traps" })]);
          var tul = h("ul");
          b.exam_traps.forEach(function (p) { tul.appendChild(h("li", { text: p })); });
          tp.appendChild(tul); card.appendChild(tp);
        }
        var foot = h("div", { class: "edu-foot" });
```

- [ ] **Step 2: Add the CSS**

In `web/course.html`, after the rule `.edu .mark-read:hover { border-color: var(--accent-deep); }` (the Phase 1 mark-as-read block), add:

```css
    .edu-worked { margin-top: 16px; padding: 2px 0 2px 12px; border-left: 2px solid var(--accent-deep); }
    .edu-hooks, .edu-traps { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--line); }
    .edu-worked h5, .edu-hooks h5, .edu-traps h5 { margin: 0 0 8px; font-family: var(--mono); font-size: 11px;
      text-transform: uppercase; letter-spacing: .12em; color: var(--dim); font-weight: 600; }
    .edu-traps h5 { color: var(--warn); }
    .edu-worked .body { color: #c4cad2; font-size: 13.5px; line-height: 1.65; }
    .edu-hooks ul, .edu-traps ul { margin: 0; padding-left: 18px; color: #c4cad2; font-size: 13px; line-height: 1.6; }
    .edu-hooks li, .edu-traps li { margin: 0 0 5px; }
```

- [ ] **Step 3: Verify lint**

Run: `npm run lint`
Expected: exit 0 (no new `no-unused-vars`/`no-undef`). The blocks are backward-compatible (render nothing when the fields are absent), so this is safe to land before content exists.

- [ ] **Step 4: Commit**

```bash
git add web/course.js web/course.html
git commit -m "feat(course): render module depth blocks (worked example, memory hooks, exam traps)"
```

---

## Task 2: Content Batch A — physics core

**Files:**
- Modify: `data/course_content.json` (4 education bodies)

**Interfaces:**
- Produces: `worked_example` / `memory_hooks` / `exam_traps` on the four Batch A bodies, matching the Task 1 render field names exactly.

**Modules (match by exact `body.title`):**
- "Pulse sequences: SE, FSE, GRE, EPI and how they are built"
- "Data acquisition: k-space, encoding and the Fourier transform"
- "MRI instrumentation: magnet, gradients, RF and coils"
- "Flip angle: the Ernst angle and the SAR trade-off" (use the exemplar above verbatim)

- [ ] **Step 1: Author the three fields for each of the four modules**

Write accurate, exam-relevant content per the Global Constraints and the quality exemplar: 1 `worked_example` (HTML `<p>…</p>`), 2–3 `memory_hooks`, 2–3 `exam_traps` per module. Content must be correct MRI physics grounded in each module's topic (k-space/Fourier encoding for Data acquisition; magnet/gradient/RF/coil hardware for Instrumentation; SE vs FSE vs GRE vs EPI mechanics for Pulse sequences). No em dashes.

- [ ] **Step 2: Apply the edits via a load → mutate → dump script**

Run this from the repo root, with the `depth` dict filled in with your authored content (the "Flip angle" entry is the exemplar verbatim):

```python
python3 - <<'PY'
import json
P = "data/course_content.json"
d = json.load(open(P))
depth = {
  "Pulse sequences: SE, FSE, GRE, EPI and how they are built": {
    "worked_example": "<p>…</p>",
    "memory_hooks": ["…", "…"],
    "exam_traps": ["…", "…"],
  },
  "Data acquisition: k-space, encoding and the Fourier transform": {
    "worked_example": "<p>…</p>", "memory_hooks": ["…","…"], "exam_traps": ["…","…"],
  },
  "MRI instrumentation: magnet, gradients, RF and coils": {
    "worked_example": "<p>…</p>", "memory_hooks": ["…","…"], "exam_traps": ["…","…"],
  },
  "Flip angle: the Ernst angle and the SAR trade-off": {
    "worked_example": "<p>You are running a T1-weighted spoiled gradient echo of the brain with a short TR of 8 ms. At a 90 degree flip the longitudinal magnetization barely recovers between pulses, so the signal is weak. Lowering the flip toward the Ernst angle for white matter, roughly 12 to 15 degrees at that TR, restores signal. The Ernst angle is the flip that maximizes steady-state signal for a given TR and T1, where cos(Ernst) equals exp(-TR/T1). A short TR pushes the Ernst angle small, which is why fast gradient echo uses low flip angles.</p>",
    "memory_hooks": [
      "Short TR wants a small flip. As TR drops, the Ernst angle drops with it.",
      "cos of the Ernst angle equals E1, and E1 is exp(-TR over T1)."
    ],
    "exam_traps": [
      "SAR scales with the square of the flip angle and with the square of field strength, so trimming the flip angle is the fastest way to cut SAR.",
      "The Ernst angle maximizes signal, not contrast. A higher flip can give stronger T1 weighting even though total signal is lower."
    ],
  },
}
n = 0
for it in d["items"]:
    if it.get("kind") == "education":
        t = it["body"]["title"]
        if t in depth:
            it["body"].update(depth.pop(t)); n += 1
assert not depth, ("unmatched titles:", list(depth))
assert n == 4, ("expected 4 updates, got", n)
open(P, "w").write(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print("updated", n, "modules")
PY
```

- [ ] **Step 3: Verify the batch (schema, count, no dashes, JSON valid)**

```python
python3 - <<'PY'
import json, re
d = json.load(open("data/course_content.json"))
DASH = re.compile(r"[—–]")
titles = {
  "Pulse sequences: SE, FSE, GRE, EPI and how they are built",
  "Data acquisition: k-space, encoding and the Fourier transform",
  "MRI instrumentation: magnet, gradients, RF and coils",
  "Flip angle: the Ernst angle and the SAR trade-off",
}
seen = 0
for it in d["items"]:
    if it.get("kind") == "education" and it["body"]["title"] in titles:
        b = it["body"]; seen += 1
        assert isinstance(b.get("worked_example"), str) and b["worked_example"].strip(), b["title"]
        assert isinstance(b.get("memory_hooks"), list) and 1 <= len(b["memory_hooks"]) <= 3, b["title"]
        assert isinstance(b.get("exam_traps"), list) and 1 <= len(b["exam_traps"]) <= 3, b["title"]
        blob = b["worked_example"] + " " + " ".join(b["memory_hooks"]) + " " + " ".join(b["exam_traps"])
        assert not DASH.search(blob), ("em/en dash in", b["title"])
assert seen == 4, ("expected 4, saw", seen)
print("Batch A OK")
PY
```

Expected: `Batch A OK`.

- [ ] **Step 4: Commit**

```bash
git add data/course_content.json
git commit -m "content(course): depth for physics-core modules (Batch A)"
```

---

## Task 3: Content Batch B — contrast & image quality

**Files:**
- Modify: `data/course_content.json` (4 education bodies)

**Modules (match by exact `body.title`):**
- "Contrast & weighting: the exam synthesis"
- "Image quality: SNR, CNR, resolution & the trade-offs"
- "Fat suppression: STIR, spectral, Dixon and water excitation"
- "MRI contrast agents: gadolinium, safety and special agents"

- [ ] **Step 1: Author the three fields for each module**

Same standards and quantities as Task 2. Ground each in its topic: TR/TE/TI driving T1/T2/PD weighting; SNR/CNR/resolution/scan-time trade-offs; STIR vs spectral fat-sat vs Dixon vs water excitation (and when each fails); gadolinium mechanism, NSF/eGFR screening, and special agents. No em dashes.

- [ ] **Step 2: Apply the edits**

Use the same `python3 - <<'PY' … PY` load → mutate → dump script as Task 2 Step 2, with the `depth` dict keyed by these four exact titles and your authored content, and the final `assert n == 4`.

- [ ] **Step 3: Verify the batch**

Use the Task 2 Step 3 verification script with `titles` set to these four exact titles (and change the printed label to `Batch B OK`). Expected: `Batch B OK`.

- [ ] **Step 4: Commit**

```bash
git add data/course_content.json
git commit -m "content(course): depth for contrast & image-quality modules (Batch B)"
```

---

## Task 4: Content Batch C — reading & protocols

**Files:**
- Modify: `data/course_content.json` (4 education bodies)

**Modules (match by exact `body.title`):**
- "Reading pathology: where lesions hide and what lights them up"
- "Regional anatomy: planes and sequences by body part"
- "Building a protocol: why each sequence is there"
- "3D imaging and reconstruction: volumes, MIP and reformats"

- [ ] **Step 1: Author the three fields for each module**

Same standards and quantities. Ground each: which sequences make which lesions bright/dark and where lesions hide; standard planes and sequence choices by body part; why each sequence earns its place in a protocol; 3D acquisition, MIP, and reformats (and their pitfalls). No em dashes.

- [ ] **Step 2: Apply the edits**

Same load → mutate → dump script as Task 2 Step 2, keyed by these four exact titles, `assert n == 4`.

- [ ] **Step 3: Verify the batch**

Task 2 Step 3 script with `titles` = these four (label `Batch C OK`). Expected: `Batch C OK`.

- [ ] **Step 4: Commit**

```bash
git add data/course_content.json
git commit -m "content(course): depth for reading & protocol modules (Batch C)"
```

---

## Task 5: Content Batch D — flow, safety & care

**Files:**
- Modify: `data/course_content.json` (4 education bodies)

**Modules (match by exact `body.title`):**
- "Flow, function and artifacts: MRA methods and the artifacts to name"
- "MR angiography and venography: TOF, PC and contrast methods"
- "MR safety: the exam-focused overview"
- "Patient care: screening to monitoring"

- [ ] **Step 1: Author the three fields for each module**

Same standards and quantities. Ground each: flow phenomena and the named artifacts (aliasing, ghosting, chemical shift, etc.); TOF vs PC vs contrast-enhanced MRA/MRV mechanics and when each is used; MR safety zones, ferromagnetic hazards, implant screening, gradient/RF bioeffects; patient screening, monitoring, contrast reactions and care. Safety and care content must be clinically correct. No em dashes.

- [ ] **Step 2: Apply the edits**

Same load → mutate → dump script as Task 2 Step 2, keyed by these four exact titles, `assert n == 4`.

- [ ] **Step 3: Verify the batch**

Task 2 Step 3 script with `titles` = these four (label `Batch D OK`). Expected: `Batch D OK`.

- [ ] **Step 4: Commit**

```bash
git add data/course_content.json
git commit -m "content(course): depth for flow, safety & care modules (Batch D)"
```

---

## Task 6: Data validation test

**Files:**
- Create: `tests/test_course_depth.py`

**Interfaces:**
- Consumes: `data/course_content.json` with all 16 education bodies carrying the three fields (Tasks 2–5).

- [ ] **Step 1: Write the test**

Create `tests/test_course_depth.py`:

```python
"""All 16 premium education modules must carry well-formed, dash-free depth fields
(worked_example, memory_hooks, exam_traps). Source of truth: data/course_content.json."""
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "data", "course_content.json")
DASH = re.compile(r"[—–]")  # em dash, en dash


def _edu_bodies():
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    return [it["body"] for it in data["items"] if it.get("kind") == "education"]


def test_all_education_modules_have_depth_fields():
    bodies = _edu_bodies()
    assert len(bodies) == 16, len(bodies)
    for b in bodies:
        title = b.get("title")
        assert isinstance(b.get("worked_example"), str) and b["worked_example"].strip(), title
        hooks = b.get("memory_hooks")
        assert isinstance(hooks, list) and 1 <= len(hooks) <= 3, title
        assert all(isinstance(x, str) and x.strip() for x in hooks), title
        traps = b.get("exam_traps")
        assert isinstance(traps, list) and 1 <= len(traps) <= 3, title
        assert all(isinstance(x, str) and x.strip() for x in traps), title


def test_depth_fields_have_no_em_dashes():
    for b in _edu_bodies():
        blob = " ".join([b.get("worked_example", "")] + b.get("memory_hooks", []) + b.get("exam_traps", []))
        assert not DASH.search(blob), b.get("title")
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/python -m pytest tests/test_course_depth.py -q`
Expected: PASS (2 passed). If it fails, a module is missing a field or contains an em/en dash — fix the content, not the test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_course_depth.py
git commit -m "test(course): validate education depth fields (schema + dash-free)"
```

---

## Self-Review

**Spec coverage:**
- Structured fields `worked_example`/`memory_hooks`/`exam_traps` on each education body → Tasks 2–5 (content) + data model in every content task.
- Rendering as labeled blocks on the Course material cards → Task 1.
- Content standards (accuracy, no-AI-tells, audience, quantity) → Global Constraints + each content task's Step 1 + the exemplar.
- Backward-compatible render (blocks only when present) → Task 1 Step 1 (`if (b.worked_example)` etc.).
- Data flow / owner-gated seed (not run here) → Global Constraints.
- Validation (schema + dash-free, all 16) → Task 6.
- No cache bump / SHELL note → Global Constraints.

**Placeholder scan:** The `"…"` inside the content tasks' `depth` dicts are the generative deliverable each agent authors (accurate MRI prose cannot be pre-written for all 16 in the plan); the schema, quantities, exact module titles, the fully-authored exemplar, the exact edit script, and the exact verification script are all concrete. The render (Task 1) and validation (Task 6) code is complete with no placeholders.

**Type consistency:** Field names `worked_example` (string), `memory_hooks` (list[str]), `exam_traps` (list[str]) are identical across the render (Task 1), every content task's edit/verify scripts, and the validation test (Task 6). The render reads `b.worked_example`/`b.memory_hooks`/`b.exam_traps`; the JSON writes those exact keys; the test asserts those exact keys. Module titles in the batch lists, edit scripts, and verify scripts are the exact `body.title` strings from `data/course_content.json`.
