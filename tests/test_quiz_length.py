"""Guard + tooling for the quiz answer-length rebalance.

The premium quiz bank had a pervasive "tell": the keyed answer was written as a
full explanatory phrase while distractors were terse, so the longest option was
almost always correct. These tests (a) unit-test the measure/patch tooling in
scripts/, and (b) lock in the fix: no text-quiz item may keep the keyed answer
longer than every distractor by more than a 20% margin.
"""
import copy
import importlib.util
import os

import pytest

_HERE = os.path.dirname(__file__)
_ROOT = os.path.dirname(_HERE)


def _load_script(name):
    path = os.path.join(_ROOT, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


qlt = _load_script("quiz_length_tools")
aqp = _load_script("apply_quiz_patch")


# ---- key_margin / is_text_quiz / flagged_items --------------------------- #

def test_key_margin_returns_key_and_longest_distractor_lengths():
    body = {"options": ["aaaa", "aa", "aa", "aa"], "answer": 0}
    assert qlt.key_margin(body) == (4, 2)


def test_key_margin_uses_the_keyed_index_not_position_zero():
    body = {"options": ["aa", "aa", "aaaaaa", "aa"], "answer": 2}
    assert qlt.key_margin(body) == (6, 2)


def test_is_text_quiz_excludes_non_quiz_and_image_items():
    assert qlt.is_text_quiz({"kind": "quiz", "body": {"prompt": "p"}}) is True
    assert qlt.is_text_quiz({"kind": "education", "body": {}}) is False
    assert qlt.is_text_quiz({"kind": "quiz", "body": {"img": "cq-1.jpg"}}) is False


def test_flagged_items_flags_long_key_only():
    long_key = {"kind": "quiz", "body": {"options": ["a" * 40, "b" * 10, "c" * 10, "d" * 10], "answer": 0}}
    balanced = {"kind": "quiz", "body": {"options": ["a" * 12, "b" * 11, "c" * 11, "d" * 11], "answer": 0}}
    image = {"kind": "quiz", "body": {"img": "cq.jpg", "options": ["a" * 40, "b", "c", "d"], "answer": 0}}
    flagged = qlt.flagged_items([long_key, balanced, image])
    assert long_key in flagged
    assert balanced not in flagged
    assert image not in flagged


def test_flagged_items_respects_the_margin():
    # key 13, longest distractor 11 -> ratio 1.18 < 1.2, not flagged.
    item = {"kind": "quiz", "body": {"options": ["a" * 13, "b" * 11, "c" * 5, "d" * 5], "answer": 0}}
    assert qlt.flagged_items([item]) == []
    # key 14, longest distractor 11 -> ratio 1.27 > 1.2, flagged.
    item2 = {"kind": "quiz", "body": {"options": ["a" * 14, "b" * 11, "c" * 5, "d" * 5], "answer": 0}}
    assert qlt.flagged_items([item2]) == [item2]


# ---- apply_patch invariants --------------------------------------------- #

def _doc():
    return {"items": [
        {"topic": "t", "kind": "quiz", "ord": 1, "body": {
            "prompt": "Q1?", "options": ["Right long answer here", "wrong a", "wrong b", "wrong c"],
            "answer": 0, "explain": "because."}},
        {"topic": "t", "kind": "quiz", "ord": 2, "body": {
            "prompt": "Q2 with image", "img": "cq-1.jpg",
            "options": ["x", "y", "z", "w"], "answer": 1, "explain": "e"}},
    ]}


def test_apply_patch_changes_only_option_text():
    doc = _doc()
    patch = [{"prompt": "Q1?", "options": ["Right", "A plausible wrong answer", "Another wrong one", "A third wrong"]}]
    n = aqp.apply_patch(patch, doc)
    assert n == 1
    item = doc["items"][0]
    assert item["body"]["answer"] == 0
    assert item["body"]["prompt"] == "Q1?"
    assert item["body"]["explain"] == "because."
    assert item["body"]["options"] == ["Right", "A plausible wrong answer", "Another wrong one", "A third wrong"]


def test_apply_patch_rejects_option_count_change():
    doc = _doc()
    with pytest.raises((ValueError, AssertionError)):
        aqp.apply_patch([{"prompt": "Q1?", "options": ["a", "b", "c"]}], doc)


def test_apply_patch_rejects_unknown_prompt_and_does_not_mutate():
    doc = _doc()
    before = copy.deepcopy(doc)
    with pytest.raises((ValueError, KeyError, AssertionError)):
        aqp.apply_patch([{"prompt": "no such prompt", "options": ["a", "b", "c", "d"]}], doc)
    assert doc == before


def test_apply_patch_will_not_target_an_image_item():
    doc = _doc()
    with pytest.raises((ValueError, KeyError, AssertionError)):
        aqp.apply_patch([{"prompt": "Q2 with image", "options": ["a", "b", "c", "d"]}], doc)


# ---- the permanent guard ------------------------------------------------- #

def test_no_answer_length_tell():
    """After the rebalance, no text-quiz item keeps the keyed answer longer than
    every distractor by more than the 20% margin. Any new item that reintroduces
    the tell fails here."""
    items = qlt.load()["items"]
    flagged = qlt.flagged_items(items)
    assert flagged == [], (
        "%d text-quiz items still have the keyed answer as the longest option by >20%%: %s"
        % (len(flagged), [it["body"]["prompt"][:60] for it in flagged[:10]])
    )
