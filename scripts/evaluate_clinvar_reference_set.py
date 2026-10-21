#!/usr/bin/env python3
"""Run internal source-fidelity contracts against the production annotation path."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from allelio.reference_evaluation import evaluate_reference_set


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--trusted-manifest", type=Path, default=ROOT / "data/evaluation/clinvar-reference-v1.manifest.json")
    parser.add_argument("--protocol", type=Path, default=ROOT / "data/evaluation/clinvar-reference-evaluation-v1.protocol.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = evaluate_reference_set(args.bundle, args.trusted_manifest, args.protocol, args.output)
    except Exception:
        print("Evaluation failed; no complete report was produced. Check the local inputs and protocol.", file=sys.stderr)
        return 2
    print("Internal case contracts: %d passed, %d failed; batch accounting %s." %
          (report["cases"]["passed"], report["cases"]["failed"], "PASS" if report["passed"] else "FAIL"))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
