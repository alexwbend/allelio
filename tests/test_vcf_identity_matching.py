"""Missing/mismatched reference identity must not turn into a copy count."""
from dataclasses import replace
import pytest
from allelio.analysis.lookup import _select_clinvar_rows
from allelio.parsers.base import VCFEvidence

EVIDENCE = VCFEvidence('A', ('G',), (0, 1), ('A', 'G'), False,
                       reference_declaration='GRCh38')
ROW = dict(rsid='rs1', ref_allele='A', alt_allele='G', assembly='GRCh38',
           chromosome='1', position_vcf=100, clinical_significance='Pathogenic')


@pytest.mark.parametrize('declaration,chrom,position,changes,expected', [
    ('GRCh38', '1', 100, {}, 1),
    ('hg38', 'chr1', 100, {}, 1),
    ('GRCh37', '1', 100, {'assembly':'GRCh37'}, 1),
    ('hg19', '1', 100, {'assembly':'GRCh37'}, 1),
    ('GRCh37', '1', 100, {}, None),
    (None, '1', 100, {}, None),
    ('file:///GRCh38.fa', '1', 100, {}, None),
    ('unknown_GRCh38', '1', 100, {}, None),
    ('GRCh38', '2', 100, {}, None),
    ('GRCh38', '1', 101, {}, None),
    ('GRCh38', '1', 100, {'assembly':None}, None),
    ('GRCh38', '1', 100, {'position_vcf':None}, None),
    ('GRCh38', 'chrM', 100, {'chromosome':'MT'}, None),
    ('GRCh38', 'NC_000001.11', 100, {}, None),
])
def test_identity_gate(declaration, chrom, position, changes, expected):
    entries, call, is_reference = _select_clinvar_rows(
        'AG', [{**ROW, **changes}], replace(EVIDENCE, reference_declaration=declaration),
        chrom, position)
    assert entries and not is_reference
    assert call.alt_copies == expected
    if expected is None:
        assert call.zygosity == 'unknown' and call.note


def test_legacy_consumer_input_does_not_require_vcf_metadata():
    _, call, _ = _select_clinvar_rows('AG', [{**ROW, 'assembly':None}])
    assert call.alt_copies == 1
