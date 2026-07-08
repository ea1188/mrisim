"""Apply a quiz option-text patch to data/course_content.json, safely.

A patch is a JSON list of {"prompt": <verbatim existing prompt>, "options": [4 strings]}.
Rebalancing is done by rewriting option *text* only; this applier is the guard that
makes that guarantee structural rather than a matter of trust: it matches each entry
to exactly one text-quiz item by its (unique) prompt, and refuses the whole patch if
anything would change the keyed answer index, the prompt, the explanation, the option
count, or would target an image item. Subagents propose text; this script preserves
structure.

Usage: python scripts/apply_quiz_patch.py patches/quiz-batch-N.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import quiz_length_tools as qlt  # noqa: E402


def apply_patch(patch, doc):
    """Apply `patch` (list of {prompt, options}) to `doc` in place. Returns the count
    of items changed. Raises ValueError on any invariant violation, without mutating
    `doc` (all checks run before any write)."""
    by_prompt = {}
    for it in doc["items"]:
        if qlt.is_text_quiz(it):
            by_prompt[it["body"]["prompt"]] = it

    # Validate everything first; only mutate once the whole patch is known-good.
    planned = []
    for entry in patch:
        prompt = entry.get("prompt")
        options = entry.get("options")
        if prompt not in by_prompt:
            raise ValueError("patch prompt not found among text-quiz items: %r" % (prompt,))
        item = by_prompt[prompt]
        if not isinstance(options, list) or len(options) != len(item["body"]["options"]) or len(options) != 4:
            raise ValueError("patch for %r must supply exactly 4 options (got %r)"
                             % (prompt, None if options is None else len(options)))
        if not all(isinstance(o, str) and o.strip() for o in options):
            raise ValueError("patch for %r has an empty/non-string option" % (prompt,))
        planned.append((item, options))

    for item, options in planned:
        item["body"]["options"] = list(options)
    return len(planned)


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8") as fh:
        patch = json.load(fh)
    doc = qlt.load()
    n = apply_patch(patch, doc)
    qlt.dump(doc)
    remaining = len(qlt.flagged_items(doc["items"]))
    print("applied %d item(s); flagged remaining: %d" % (n, remaining))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
