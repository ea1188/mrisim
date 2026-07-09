"""Guard against the answer-length "tell" in the FREE quiz bank (web/quiz.json).

The free quiz shuffles option order at render (web/quiz.js), so answer POSITION
is not a tell. But shuffling does not change option LENGTH: if the keyed answer
is consistently the longest option, a test-taker can game the bank by picking the
longest choice. This locks in the rebalance: no question may keep the keyed answer
longer than every distractor by more than a 20% margin.

The premium bank has its own guard (tests/test_quiz_length.py); this covers the
separately-shaped free pool, whose items are flat {options, answer} objects.
"""
import json
import os

MARGIN = 1.2
_ROOT = os.path.dirname(os.path.dirname(__file__))
_QUIZ = os.path.join(_ROOT, "web", "quiz.json")


def _load():
    with open(_QUIZ, encoding="utf-8") as fh:
        return json.load(fh)["questions"]


def _key_over_margin(q):
    """Return (keylen, longest_distractor_len) if the key is too long, else None."""
    opts, ai = q["options"], q["answer"]
    key = len(opts[ai])
    longest = max(len(o) for i, o in enumerate(opts) if i != ai)
    return (key, longest) if key > MARGIN * longest else None


def test_no_free_quiz_answer_length_tell():
    offenders = []
    for i, q in enumerate(_load()):
        over = _key_over_margin(q)
        if over:
            offenders.append((i, q["category"], *over))
    assert not offenders, (
        "keyed answer is the longest option by >20% in these free-quiz items "
        "(index, category, keylen, longest_distractor): " + repr(offenders)
    )


def test_free_quiz_structural_invariants():
    for i, q in enumerate(_load()):
        assert len(q["options"]) == 4, f"q{i} does not have exactly 4 options"
        assert isinstance(q["answer"], int) and 0 <= q["answer"] < 4, f"q{i} bad answer index"
