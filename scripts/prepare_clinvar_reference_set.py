#!/usr/bin/env python3
"""Freeze the pinned internal ClinVar source-fidelity set; no annotation or AI run."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from allelio.clinvar_reference import build_reference_set


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=ROOT / "data/evaluation/clinvar-reference-v1.protocol.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_reference_set(args.source, args.protocol, args.output)
    print("Frozen %d reference records and %d constructed cases; no evaluation executed." %
          (result["selection_counts"]["selected_records"], result["case_counts"]["total"]))


if __name__ == "__main__":
    main()
