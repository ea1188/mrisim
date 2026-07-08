# Quiz Answer-Length Rebalance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the answer-length "tell" from the 170 flagged premium quiz items by rebalancing
option text, without changing any keyed answer, prompt, or explanation.

**Architecture:** Deterministic tooling (measure helpers + invariant-enforcing patch applier +
pytest guard) built first and inline; then a batched content pass where each Fable subagent writes
a patch of balanced option text and a Fable accuracy reviewer verifies medical correctness. Patches
apply through the applier, which guarantees structure so subagents only ever touch text.

**Tech Stack:** Python 3 (stdlib json), pytest; subagents on Fable for content; Supabase MCP for
re-seed.

## Global Constraints

- `data/course_content.json` is the SOURCE (jsonb `body`, no migration). Round-trip with
  `json.dumps(d, indent=2, ensure_ascii=False) + "\n"` for byte-identical minimal diffs.
- NEVER change a keyed `answer` index, a `prompt`, an `explain`, option count (always 4), or any
  non-body field. Only option *text* changes.
- Do NOT touch the 17 image items (`kind=="quiz"` with `body.img`, `cq-*.jpg`).
- Content voice: no em dashes, no AI-tell punctuation, natural exam prose (feedback_no_ai_tells_content).
- Distractors must stay unambiguously wrong but plausible; no new correct answer, no joke options.
- Guard threshold: an item is "flagged" when the keyed option length > 1.2 × the longest distractor
  length. Target end state: 0 flagged text items.
- Subagents on Fable (feedback_use_fable_subagents); final whole-branch review on Opus.

---

### Task 1: Measure helpers + guard tooling

**Files:**
- Create: `scripts/quiz_length_tools.py`
- Create: `tests/test_quiz_length.py`

**Interfaces:**
- Produces: `flagged_items(items, margin=1.2) -> list[dict]`; `key_margin(body) -> tuple[int,int]`
  (returns `(key_len, max_distractor_len)`); `is_text_quiz(item) -> bool`;
  `load(path="data/course_content.json") -> dict`; `dump(d, path=...) -> None`.

- [ ] **Step 1: Write failing tests** in `tests/test_quiz_length.py`:
  - `test_key_margin_basic`: body with options `["aaaa","aa","aa","aa"]`, answer 0 →
    `key_margin(body) == (4, 2)`.
  - `test_flagged_items_flags_long_key`: one text-quiz item with key 4× the distractors is returned;
    one with balanced options is not; an item with `body.img` is never returned.
  - `test_no_answer_length_tell`: `flagged_items(load()["items"])` — assert it is a list (this test
    starts RED with ~170 and becomes the permanent guard; for Task 1 assert `isinstance(list)` only,
    tighten to `== []` in Task 5).
- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_quiz_length.py -q` → import error.
- [ ] **Step 3: Implement** `scripts/quiz_length_tools.py`:
  - `is_text_quiz(item)`: `item.get("kind")=="quiz" and not item.get("body",{}).get("img")`.
  - `key_margin(body)`: `ka=body["answer"]; klen=len(body["options"][ka]);
    others=[len(o) for i,o in enumerate(body["options"]) if i!=ka]; return (klen, max(others))`.
  - `flagged_items(items, margin=1.2)`: text-quiz items where `k > margin*m` for `(k,m)=key_margin`.
  - `load`/`dump` per Global Constraints.
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** `feat(quiz): answer-length measure helpers + guard scaffold`.

### Task 2: Invariant-enforcing patch applier

**Files:**
- Create: `scripts/apply_quiz_patch.py`
- Modify: `tests/test_quiz_length.py` (add applier tests)

**Interfaces:**
- Consumes: Task 1 helpers.
- Produces: `apply_patch(patch, doc) -> int` (mutates `doc` in place, returns count changed, raises
  `ValueError`/`AssertionError` on any invariant violation); CLI `python scripts/apply_quiz_patch.py
  <patch.json>` loads the source doc, applies, dumps.

- [ ] **Step 1: Write failing tests:**
  - `test_apply_patch_changes_only_option_text`: fixture doc + patch rewording options of one item
    (same order, same count) → item's `answer`, `prompt`, `explain` unchanged, options equal patch.
  - `test_apply_patch_rejects_option_count_change`: patch with 3 options → raises.
  - `test_apply_patch_rejects_unknown_prompt`: patch prompt not in doc → raises, doc unmutated.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** `apply_patch(patch, doc)`: build `{prompt: item}` over text-quiz items;
  for each patch entry assert prompt present, `len(options)==len(item["body"]["options"])==4`, then
  set `item["body"]["options"] = list(options)`; leave `answer/prompt/explain` untouched; return
  count. CLI wraps `load` → `apply_patch` → `dump`, prints changed count and remaining flagged count.
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** `feat(quiz): invariant-enforcing option-patch applier`.

### Task 3: Extract flagged items into batch briefs (controller, inline)

Not a code task — the controller runs `flagged_items(load()["items"])`, splits into ordered slices
of ~17, and writes one brief file per batch under the job tmp dir. Each brief lists, per item:
verbatim prompt, the 4 options with the keyed one marked and each option's current length, and the
explanation. No code committed.

### Tasks 4.1 … 4.N: Content batches (one per ~17 items, Fable)

Repeat per batch N:
- [ ] Dispatch Fable **implementer**: read brief N; write `patches/quiz-batch-N.json`
  (`[{prompt, options[4]}]`) rebalancing lengths per Global Constraints; report the patch path.
- [ ] Controller runs `python scripts/apply_quiz_patch.py patches/quiz-batch-N.json`; abort-on-error.
- [ ] Dispatch Fable **accuracy reviewer**: given the batch's before/after options + explanations,
  confirm per item — keyed option still the single correct answer, every distractor still wrong but
  plausible, lengths balanced (no key >1.2× longest distractor), no em dashes / AI tells. Report
  per-item PASS or a fix list.
- [ ] Fix loop: revise flagged items in the patch, re-apply, re-review until clean.
- [ ] Commit `content(quiz): rebalance option lengths, batch N (no answer changes)`.
- [ ] Append `Batch N: complete, remaining flagged = <count>` to the SDD ledger.

### Task 5: Lock the guard + full test/lint

**Files:** Modify `tests/test_quiz_length.py`.

- [ ] Tighten `test_no_answer_length_tell` to assert `flagged_items(load()["items"]) == []`.
- [ ] Run `python -m pytest tests/test_quiz_length.py -q` → green.
- [ ] Run `ruff check src/ tests/ scripts/` and `python -m pytest -q` (full suite) → green.
- [ ] Commit `test(quiz): lock answer-length guard to zero`.

### Task 6: Whole-branch review + re-seed + merge

- [ ] Opus whole-branch review of every option-text change (accuracy + tells + no structural drift).
- [ ] Re-seed changed rows to Supabase `course_content` via MCP `execute_sql` UPDATE matched by
  `body->>'prompt'` (only the flagged prompts).
- [ ] Push, open PR, merge on green.

## Self-Review

- Spec coverage: helpers (T1), applier (T2), extraction (T3), content pass + accuracy review
  (T4.x), guard lock + lint (T5), review + re-seed (T6) — all spec sections covered.
- Placeholder scan: batch count N resolved at extraction time from the live flagged count; no TODOs.
- Type consistency: `flagged_items`/`key_margin`/`apply_patch` signatures identical across tasks.
