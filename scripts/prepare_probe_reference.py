#!/usr/bin/env python3
"""Verify sourced probe identities against explicit ClinVar build placements."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from allelio.probe_reference import prepare_reference_mapping


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mapping', help='Already sourced mapping with explicit native-build alleles')
    parser.add_argument('clinvar', help='Local ClinVar variant_summary source file')
    parser.add_argument('--output', required=True, help='New directory for mapping and decisions')
    args = parser.parse_args()
    directory = Path(args.output)
    directory.mkdir(parents=True, exist_ok=False)
    mapping, report = prepare_reference_mapping(args.mapping, args.clinvar)
    (directory / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    if report['admitted_rows']:
        (directory / 'mapping.json').write_text(json.dumps(mapping, indent=2) + '\n')
    print(f"Verified {report['admitted_rows']}/{report['input_rows']} mapping rows; see verification.json.")
    return 0 if report['admitted_rows'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
