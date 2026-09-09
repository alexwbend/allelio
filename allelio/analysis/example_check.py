"""Check a database's results for the example file against expected_findings.json.

Shared by tests/test_example_recall.py (small fixture database, runs in CI)
and scripts/check_example.py (the user's full local database). Pure
comparison: builds nothing, prints nothing.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from allelio.analysis.lookup import analyze_variants_with_stats
from allelio.parsers.base import parse_genotype_file_with_stats

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_FILE = ROOT / "examples" / "example_23andme.txt"
EXPECTED_FILE = ROOT / "examples" / "expected_findings.json"


def load_expected() -> Dict[str, Any]:
    return json.loads(EXPECTED_FILE.read_text())


def run_example(db, example_file: Path = EXAMPLE_FILE):
    """Parse the example and analyse it with default options.

    Returns (results, analysis_stats, parse_stats).
    """
    variants, parse_stats = parse_genotype_file_with_stats(str(example_file))
    results, stats = analyze_variants_with_stats(variants, db)
    return results, stats, parse_stats, variants


def compare(db, expected: Dict[str, Any] = None) -> List[Tuple[str, bool, str]]:
    """Return one (check, passed, detail) row per expectation."""
    expected = expected or load_expected()
    results, stats, parse_stats, variants = run_example(db)
    by_rsid = {r.rsid: r for r in results}
    rows: List[Tuple[str, bool, str]] = []

    want = expected["stats"]
    rows.append(("parsed_variants", len(variants) == want["parsed_variants"], f"{len(variants)} vs {want['parsed_variants']}"))
    i_rows = parse_stats.i_id_rows if parse_stats else 0
    rows.append(("i_id_rows", i_rows == want["i_id_rows"], f"{i_rows} vs {want['i_id_rows']}"))
    for key in ("annotated_sites", "reference_genotype_sites", "zygosity_unknown_sites"):
        got = getattr(stats, key)
        rows.append((key, got == want[key], f"{got} vs {want[key]}"))

    for rsid, exp in expected["sites"].items():
        r = by_rsid.get(rsid)
        if not exp["reported"]:
            rows.append((f"{rsid} not reported", r is None, "reported" if r else "absent"))
            continue
        if r is None:
            rows.append((f"{rsid} reported", False, "missing from results"))
            continue
        rows.append((f"{rsid} reported", True, r.describe_zygosity()))
        if exp.get("category") is not None:
            rows.append((f"{rsid} category", r.category == exp["category"], f"{r.category} vs {exp['category']}"))
        for field in ("zygosity", "alt_copies", "matched_allele", "allele_role"):
            if field in exp:
                got = getattr(r, field)
                rows.append((f"{rsid} {field}", got == exp[field], f"{got!r} vs {exp[field]!r}"))
    return rows
