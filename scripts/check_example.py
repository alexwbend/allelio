#!/usr/bin/env python3
"""Run the example file against your full local database and check the answers.

    python3 scripts/check_example.py

Same expectations as the test suite (examples/expected_findings.json), but
against the real ClinVar / GWAS Catalog / gnomAD copies under ~/.allelio/data
rather than the fixture excerpts, so a reviewer can confirm the shipped
database reproduces the documented findings. Exit status 1 on any mismatch.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from allelio.analysis.example_check import compare, load_expected  # noqa: E402
from allelio.database.store import AllelioDB  # noqa: E402


def main() -> int:
    db = AllelioDB()
    if not db.is_initialized():
        print("Database not initialised, run `allelio setup` first.")
        return 2
    print(f"Reference data: {db.describe_sources()}\n")
    rows = compare(db, load_expected())
    failed = 0
    for name, ok, detail in rows:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<38} {detail}")
        failed += 0 if ok else 1
    print(f"\n{len(rows) - failed}/{len(rows)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
