"""Measure helpers for the quiz answer-length "tell".

data/course_content.json is the source of truth for the premium quiz bank. A
long-standing item-writing flaw made the keyed answer the longest option far too
often, so a test-wise candidate could game the bank by picking the longest choice.
These helpers define, in one place, what "flagged" means (shared by the rebalance
tooling and the permanent pytest guard) and load/save the source with byte-stable
formatting so content diffs stay minimal.
"""
import json
import os

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "course_content.json")

# An item counts as flagged when the keyed answer is longer than every distractor
# by more than this ratio (20%). Killing the *signal* is the goal, not exact-equal
# lengths, so a key that is only slightly longest is acceptable.
MARGIN = 1.2


def is_text_quiz(item):
    """A quiz item that carries text options (not an image "read-the-scan" item)."""
    return item.get("kind") == "quiz" and not item.get("body", {}).get("img")


def key_margin(body):
    """(length of the keyed option, length of the longest distractor)."""
    ka = body["answer"]
    key_len = len(body["options"][ka])
    others = [len(o) for i, o in enumerate(body["options"]) if i != ka]
    return key_len, (max(others) if others else 0)


def flagged_items(items, margin=MARGIN):
    """Text-quiz items whose keyed answer is longer than every distractor by >margin."""
    out = []
    for it in items:
        if not is_text_quiz(it):
            continue
        key_len, longest = key_margin(it["body"])
        if key_len > margin * longest:
            out.append(it)
    return out


def load(path=DATA_PATH):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def dump(doc, path=DATA_PATH):
    """Write back with the project's byte-stable formatting (minimal diffs)."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    _doc = load()
    _flagged = flagged_items(_doc["items"])
    _text = [it for it in _doc["items"] if is_text_quiz(it)]
    print("text quiz items: %d | flagged (key longest by >%.0f%%): %d"
          % (len(_text), (MARGIN - 1) * 100, len(_flagged)))
