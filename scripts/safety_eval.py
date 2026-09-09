#!/usr/bin/env python3
"""Score the lexical safety filter against the labelled sentence set.

Reads tests/fixtures/safety_sentences.json, runs every sentence through
``allelio.ai.safety.find_unsafe_language``, and prints the catch rate on the
unsafe sentences (by category) and the false-positive rate on the safe ones.
The same numbers are asserted by tests/test_safety.py; this script exists so
the figures quoted in the paper can be regenerated with one command:

    python3 scripts/safety_eval.py

Exit status is 1 if any sentence is misclassified, so it can gate CI.
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from allelio.ai.safety import find_unsafe_language  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "safety_sentences.json"


def main() -> int:
    data = json.loads(FIXTURE.read_text())
    unsafe = data["unsafe"]
    safe = data["safe"]

    caught = Counter()
    total = Counter()
    misses = []
    for item in unsafe:
        total[item["category"]] += 1
        matches = find_unsafe_language(item["text"])
        if matches:
            caught[item["category"]] += 1
        else:
            misses.append(item)

    false_positives = [(t, find_unsafe_language(t)) for t in safe if find_unsafe_language(t)]

    print(f"Labelled set: {len(unsafe)} unsafe, {len(safe)} safe sentences\n")
    print("Catch rate on unsafe sentences:")
    for category in ("diagnostic", "prognostic", "prescriptive"):
        n, c = total[category], caught[category]
        print(f"  {category:<13} {c:>3}/{n:<3} ({100.0 * c / n if n else 0:.0f}%)")
    n, c = sum(total.values()), sum(caught.values())
    print(f"  {'overall':<13} {c:>3}/{n:<3} ({100.0 * c / n:.1f}%)")
    print(f"\nFalse positives on safe sentences: {len(false_positives)}/{len(safe)} "
          f"({100.0 * len(false_positives) / len(safe):.1f}%)")

    for item in misses:
        print(f"  MISSED  [{item['category']}] {item['text']}")
    for text, matches in false_positives:
        print(f"  FLAGGED [{matches[0].category}: {matches[0].text!r}] {text}")

    return 1 if (misses or false_positives) else 0


if __name__ == "__main__":
    sys.exit(main())
