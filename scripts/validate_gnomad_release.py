#!/usr/bin/env python3
"""Validate a completed, unpublished format-2 release before uploading it.

Checks artifact checksum, provenance, complete row identity, source counts,
duplicate identities, selected-site coverage and the public example's anchors.
Prints a machine-readable report and exits nonzero on contradictions. Missing
selected sites are explicitly reported; they require inspection before release.
"""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from allelio.database.downloader import sha256_file
from allelio.database.gnomad import parse_gnomad, gnomad_file_header
from allelio.analysis.frequency import valid_frequency


def validate(manifest_path):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    artifact = manifest_path.parent / manifest['file']
    errors, counts, seen, rsids, example = [], Counter(), set(), set(), {}
    if sha256_file(str(artifact)) != manifest.get('sha256'):
        return {'errors':['artifact checksum mismatch']}
    header = gnomad_file_header(str(artifact))
    if (manifest.get('format') != 2 or header != {'format':'2', 'assembly':manifest.get('assembly'), 'source_version':manifest.get('version')}):
        errors.append('unexpected extract format, assembly or release')
    raw_rows = 0
    with gzip.open(artifact, 'rt') as source:
        for line in source:
            if not line.startswith('##') and not line.startswith('rsid\t'):
                raw_rows += 1
    for row in parse_gnomad(str(artifact)):
        identity = tuple(row[k] for k in ('rsid','assembly','chromosome','position','ref_allele','alt_allele'))
        if not all(identity) or row['ref_allele']==row['alt_allele']:
            errors.append('incomplete/degenerate identity: '+str(identity))
        if identity in seen:
            errors.append('duplicate identity: '+str(identity))
        seen.add(identity)
        rsids.add(row['rsid'])
        counts[row['chromosome']] += 1
        if row['allele_frequency'] is not None and not valid_frequency(row['allele_frequency']):
            errors.append('invalid frequency: '+str(identity))
        if row['rsid'] in ('rs7412','rs28897696','rs429358','rs1799945'):
            example.setdefault(row['rsid'],[]).append(row)
    if raw_rows != len(seen) or raw_rows != manifest.get('rows'):
        errors.append('raw, imported and manifest row counts differ')
    selected_file = manifest_path.parent / 'selected-rsids.txt'
    selected = set(selected_file.read_text().splitlines())
    unexpected = sorted(rsids-selected)
    missing = sorted(selected-rsids)
    if unexpected:
        errors.append(f'{len(unexpected)} rsIDs not in the declared selection')
    if missing:
        errors.append(f'{len(missing)} selected rsIDs missing; inspect before publishing')
    for rsid, ref, alt in [('rs7412','C','T'),('rs28897696','G','A'),('rs429358','T','C'),('rs1799945','C','G')]:
        if not any(row['ref_allele']==ref and row['alt_allele']==alt for row in example.get(rsid,[])):
            errors.append(f'{rsid}: expected public example allele {ref}>{alt} absent')
    return dict(errors=errors, rows=raw_rows, rsids=len(rsids), by_chromosome=dict(counts),
                missing_rsids=missing, unexpected_rsids=unexpected, example=example,
                sha256=manifest['sha256'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('--report')
    args=parser.parse_args()
    report=validate(args.manifest)
    text=json.dumps(report,indent=2,allow_nan=False)+'\n'
    if args.report:
        Path(args.report).write_text(text)
    print(text)
    sys.exit(bool(report['errors']))
