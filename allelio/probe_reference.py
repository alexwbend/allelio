"""Attach explicit ClinVar placements to an already sourced probe mapping.

This does not discover vendor aliases or infer an assay's alleles from an rsID.
"""
import copy
import csv
import gzip
from pathlib import Path

from allelio.database.downloader import sha256_file
from allelio.probes import load_mapping


def prepare_reference_mapping(mapping_path, clinvar_path):
    mapping_hash = sha256_file(str(mapping_path))
    mapping = load_mapping(mapping_path)
    source_hash = sha256_file(str(clinvar_path))
    wanted = {r['rsid'] for r in mapping['entries']}
    placements = {rsid: set() for rsid in wanted}
    opener = gzip.open if str(clinvar_path).endswith('.gz') else open
    required = {'#AlleleID', 'RS# (dbSNP)', 'Assembly', 'Chromosome',
                'PositionVCF', 'ReferenceAlleleVCF', 'AlternateAlleleVCF'}
    with opener(clinvar_path, 'rt', encoding='utf-8') as source:
        rows = csv.DictReader(source, delimiter='\t')
        if not required <= set(rows.fieldnames or []):
            raise ValueError('ClinVar source lacks explicit allele-placement columns.')
        for row in rows:
            rsid = row['RS# (dbSNP)']
            if not rsid.startswith('rs'):
                rsid = 'rs' + rsid
            if rsid not in wanted or row['Assembly'] not in ('GRCh37', 'GRCh38'):
                continue
            # Keep malformed candidate records as conflicting evidence instead
            # of silently choosing a better-looking row at the same rsID.
            placements[rsid].add(tuple(row[k] for k in (
                '#AlleleID', 'Assembly', 'Chromosome', 'PositionVCF',
                'ReferenceAlleleVCF', 'AlternateAlleleVCF')))
    if sha256_file(str(clinvar_path)) != source_hash or sha256_file(str(mapping_path)) != mapping_hash:
        raise ValueError('Mapping or reference source changed during verification.')
    output = copy.deepcopy(mapping)
    output['entries'] = []
    decisions = []
    for row in mapping['entries']:
        native = (mapping['assembly'], row['chromosome'], str(row['position']), row['ref'], row['alt'])
        records = placements[row['rsid']]
        matches = {r for r in records if r[1:] == native}
        reason = 'native_identity_unresolved'
        if len(matches) == 1:
            native_record = next(iter(matches))
            # Match the importer's GRCh38 preference, preserving distinct
            # AlleleIDs and locations rather than choosing the first row.
            ids_with_38 = {r[0] for r in records if r[1] == 'GRCh38'}
            selected = {r for r in records if r[1] == 'GRCh38' or r[0] not in ids_with_38}
            reason = 'reference_identity_ambiguous'
            if len(selected) == 1:
                reference = next(iter(selected))
                reason = 'allele_or_chromosome_changed'
                if (reference[0] == native_record[0] and reference[2] == row['chromosome']
                        and reference[4:] == (row['ref'], row['alt'])):
                    reason = 'unsupported_alleles'
                    if (len(row['ref']) == len(row['alt']) == 1
                            and set(row['ref'] + row['alt']) <= set('ACGT')
                            and row['ref'] != row['alt']
                            and {row['ref'], row['alt']} not in ({'A', 'T'}, {'C', 'G'})
                            and reference[3].isdigit() and int(reference[3]) > 0):
                        admitted = copy.deepcopy(row)
                        admitted['allele_id'] = native_record[0]
                        admitted['reference_anchor'] = {
                            'assembly': reference[1], 'chromosome': reference[2],
                            'position': int(reference[3]), 'ref': reference[4], 'alt': reference[5],
                            'allele_id': reference[0], 'source_sha256': source_hash,
                        }
                        output['entries'].append(admitted)
                        reason = 'explicit_paired_placements'
        decisions.append({'probe': row['probe'], 'rsid': row['rsid'], 'reason': reason})
    output['reference_source'] = {'source': 'ClinVar', 'file': Path(clinvar_path).name,
                                  'sha256': source_hash, 'input_mapping_sha256': mapping_hash}
    return output, {'input_rows': len(mapping['entries']), 'admitted_rows': len(output['entries']),
                    'source': output['reference_source'], 'decisions': decisions}
