# Quiz Answer-Length Rebalance — Design

**Goal:** Remove the pervasive answer-length "tell" from the premium quiz bank so a
test-taker cannot game items by picking the longest option, without changing any keyed answer,
prompt, or explanation.

**Status:** Approved 2026-07-08 (user chose "full length-rebalance as a batched build" over the
narrower ~20-item audit fix). This spec records the agreed approach; see
[[project_quiz_length_rebalance]].

## The problem (measured)

In `data/course_content.json`, of the 205 text quiz items (`kind == "quiz"`, no `img`):

- the **keyed answer is the strictly longest option on 179**, and
- **longest by a >20% margin on 170**.

Keys were written as full explanatory phrases ("Shortens the T1 of nearby tissue where it
accumulates") while distractors are terse stubs ("Suppresses fat"). Length alone carries the
answer. This is construct-irrelevant variance: it lets a test-wise candidate score above chance
without the knowledge the item is meant to measure. The 17 image items (`cq-*.jpg`) are out of
scope (their options are already short/parallel and re-rendering is unrelated).

## Fix

Rewrite **option text only** so lengths are balanced within each item — primarily by expanding
each distractor into a plausible full phrase in the same register as the key, and secondarily by
tightening a key when a parenthetical bloats it. The keyed `answer` index, the prompt, and the
explanation never change. Distractors must stay unambiguously wrong but plausible to a weak
student (no new correct answer, no joke options). Content voice per [[feedback_no_ai_tells_content]]:
no em dashes, no AI-tell punctuation, natural exam prose.

**Target:** after the pass, **0** items have the keyed answer longer than every distractor by more
than a 20% margin (the pytest guard threshold), and the mean length gap shrinks materially. A
handful of items where the key is *slightly* longest (within 20%) is acceptable and realistic;
the goal is to kill the *signal*, not to force exact-equal lengths.

## Architecture

The source of truth is `data/course_content.json` (jsonb `body`, no migration). The risk at
170-item scale is a subagent silently changing an answer index, reformatting the file, or
corrupting JSON. The design removes that risk by separating **proposal** (subagents write text)
from **application** (one script enforces structure).

```
flagged.json  ──►  batch dispatch (subagent writes patch)  ──►  patch-NN.json
                                                                     │
                                              apply_quiz_patch.py (enforces invariants)
                                                                     ▼
                                                        data/course_content.json (mutated)
                                                                     │
                                                        re-measure + pytest guard
                                                                     │
                                                     targeted MCP UPDATE of changed rows
```

### Components

1. **`scripts/quiz_length_tools.py`** — pure helpers, unit-tested:
   - `flagged_items(items, margin=1.2)` → list of flagged text-quiz items (the measure logic,
     lifted out of the throwaway one-liner so tests and the guard share one definition).
   - `key_margin(body)` → `(key_len, max_distractor_len)` for one item.
   - `load()/dump(d)` round-trip helpers using `json.dumps(d, indent=2, ensure_ascii=False)+"\n"`
     for byte-identical, minimal diffs.

2. **A patch file per batch** — `patches/quiz-batch-NN.json`, a list of
   `{"prompt": "<verbatim existing prompt>", "options": ["<4 new option strings>"]}`. The prompt
   is the match key (all 205 prompts are unique — verified). Options are given in the **same order**
   as the existing item, so the keyed `answer` index still points at the (reworded-but-same-meaning)
   correct option.

3. **`scripts/apply_quiz_patch.py`** — applies one patch file with hard assertions; refuses the
   whole patch (non-zero exit, no write) if any check fails:
   - every patch prompt matches exactly one item (`kind=="quiz"`, no `img`);
   - `len(new_options) == len(old_options) == 4`;
   - the option at the item's `answer` index changed *text* but the patch preserves order (we cannot
     verify meaning here — that is the reviewer's job — but we assert the answer index is unchanged
     and that no option became identical to a *different* item's, guarding accidental dedupe);
   - `prompt`, `answer`, `explain`, and all non-body fields are untouched;
   - writes via the round-trip dumper so the diff is only the changed option strings.

4. **`tests/test_quiz_length.py`** — the permanent guard:
   - `test_no_answer_length_tell()`: `flagged_items(load()["items"], margin=1.2)` is empty
     (0 items with key longer than every distractor by >20%). This locks the fix in — any future
     item that reintroduces the tell fails CI.
   - `test_apply_patch_preserves_invariants()`: applying a sample patch to a fixture keeps answer
     index, prompt, explain, and option count; changing an answer index or option count raises.

### Batching

The flagged set (~170) is split into batches of ~15 items. Each batch is one implementer subagent
(Fable, per [[feedback_use_fable_subagents]]) that reads its items (prompt, 4 options with the key
marked, explanation) and writes a patch file, followed by one accuracy reviewer subagent (Fable)
that confirms, per item: the keyed option is still the single correct answer, every distractor is
still wrong but plausible, lengths are balanced, and no em dashes / AI tells. Batches run
sequentially (all touch the one JSON file via the applier). This mirrors the Phase 2 depth build.

## Re-seed

After all batches apply and the guard passes, re-seed only the changed rows to Supabase
(`course_content`) via targeted MCP `execute_sql` UPDATEs, matched by `body->>'prompt'`, same
pattern as the Phase 2 seed. Owner already OKs MCP DB writes.

## Error handling / edge cases

- **Patch prompt not found / ambiguous:** applier aborts the whole patch, non-zero exit, no write.
  (Prompts are unique; a miss means the subagent altered the prompt text — a bug to fix, not apply.)
- **Reviewer rejects an item:** fix subagent revises only that item's options in the patch;
  re-apply the batch (applier is idempotent — it overwrites option text from the current patch).
- **A key genuinely cannot be shortened below the longest distractor** (rare — the correct concept
  needs the words): lengthen the distractors to match instead; the >20% margin guard, not exact
  equality, is the bar, so this is always satisfiable.
- **Storage/DB:** re-seed is best-effort and idempotent (UPDATE by prompt); a failed row can be
  re-run without side effects.

## Testing

- **Unit:** `pytest tests/test_quiz_length.py` — the guard + applier-invariant tests above.
- **Whole-bank re-measure** after each batch applies (the controller runs `flagged_items` and logs
  the remaining count in the ledger).
- **Accuracy review** per batch (subagent) — the substantive gate; medical correctness of every
  reworded distractor.
- No engine/physics change; the existing Python suite and `npm run test:web` are unaffected (no JS
  touched).

## Out of scope

- The 17 image quiz items (`cq-*.jpg`).
- Rewriting prompts or explanations, or changing any keyed answer.
- The separate "weak distractor / concept duplication" audit note (smaller, different problem; can
  follow later). This pass targets the length tell only.
- Randomizing option order at render time (a different, larger change to `web/course.js`; the
  length fix stands on its own and is the agreed scope).
