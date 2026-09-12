#!/usr/bin/env python3
"""Reproduce internal development checks; never an independent accuracy benchmark."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from allelio.analysis.example_check import build_fixture_db, compare
from allelio.ai.safety import find_unsafe_language
from allelio.parsers.vcf_parser import parse_vcf
from allelio.analysis.zygosity import call_zygosity


def run():
    cases = []
    with tempfile.TemporaryDirectory() as directory:
        db = build_fixture_db(str(Path(directory) / 'fixture.db'))
        example = [dict(check=n, passed=p, detail=d) for n, p, d in compare(db)]
        for name, gt, expected in [('haploid_alt', '1', 1),
                                   ('haploid_ref', '0', 0),
                                   ('diploid_het', '0/1', 1),
                                   ('diploid_alt', '1/1', 2)]:
            path = Path(directory) / 'case.vcf'
            path.write_text('##fileformat=VCFv4.2\n'
                            '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n'
                            f'X\t100\trs900000001\tA\tG\t.\tPASS\t.\tGT\t{gt}\n')
            variants = parse_vcf(str(path))
            actual = call_zygosity(variants[0].genotype, 'A', 'G') if variants else None
            expected_ploidy = 1 if '/' not in gt else 2
            passed = (actual is not None and actual.alt_copies == expected
                      and len(variants[0].genotype) == expected_ploidy)
            cases.append(dict(case=name, expected_copies=expected,
                              actual_copies=actual.alt_copies if actual else None,
                              expected_ploidy=expected_ploidy,
                              genotype=variants[0].genotype if variants else None,
                              passed=passed))
    labelled = json.loads((ROOT / 'tests/fixtures/safety_sentences.json').read_text())
    caught = sum(bool(find_unsafe_language(x['text'])) for x in labelled['unsafe'])
    false_positive = sum(bool(find_unsafe_language(x)) for x in labelled['safe'])
    paths = sorted(p for folder in ('allelio', 'tests/fixtures', 'examples')
                   for p in (ROOT / folder).rglob('*')
                   if p.is_file() and '__pycache__' not in p.parts
                   and p.suffix in ('.py', '.json', '.tsv', '.csv', '.gz', '.txt'))
    paths.append(Path(__file__).resolve())
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
    passed = all(x['passed'] for x in example + cases) and caught == len(labelled['unsafe']) and false_positive == 0
    return dict(schema_version=1, evidence_type='internal_development_only',
                independent_validation=False, revision=revision, working_tree_dirty=dirty,
                file_sha256=hashes, example_checks=example, vcf_challenges=cases,
                safety=dict(unsafe_total=len(labelled['unsafe']), caught=caught,
                            safe_total=len(labelled['safe']), false_positives=false_positive),
                passed=passed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Internal development checks: {'PASS' if result['passed'] else 'FAIL'}; {args.output}")
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
