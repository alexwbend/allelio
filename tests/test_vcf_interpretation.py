"""Integration tests for explicit VCF evidence in ClinVar row selection."""
import pytest
from allelio.analysis.lookup import analyze_variants_with_stats
from allelio.database.store import AllelioDB
from allelio.parsers.vcf_parser import parse_vcf


@pytest.mark.parametrize('ref,alt,gt,cv_ref,cv_alt,copies', [
    ('A', 'G', '1', 'A', 'G', 1),
    ('A', 'G', '0/0', 'A', 'G', 0),
    ('A', 'G,T', '1/2', 'A', 'G', 1),
    ('A', 'G,T', '2/2', 'A', 'G', 0),
    ('A', 'G,T', '2|1', 'A', 'T', 1),
    ('T', 'C', '1/1', 'A', 'G', None),  # No automatic complement.
    ('A', 'T', '1/1', 'A', 'G', None),  # Undeclared alternate.
    ('A', 'AG', '1', 'A', 'G', None),   # Not two SNP bases.
    ('AT', 'A', '0/1', 'AT', 'A', None),  # Normalization not yet supported.
    ('A', '<DEL>', '1/1', 'A', 'G', None),
])
def test_parser_evidence_reaches_clinvar(tmp_path, ref, alt, gt, cv_ref, cv_alt, copies):
    path = tmp_path / 'input.vcf'
    path.write_text('##fileformat=VCFv4.3\n##reference=GRCh38\n'
                    '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS\n'
                    f'1\t100\trs1\t{ref}\t{alt}\t.\tPASS\t.\tGT\t{gt}\n')
    db = AllelioDB(str(tmp_path / 'a.db'))
    db.initialize()
    db.insert_clinvar_batch([dict(rsid='rs1', ref_allele=cv_ref, alt_allele=cv_alt,
        assembly='GRCh38', chromosome='1', position_vcf=100,
        gene='EXAMPLE', clinical_significance='Pathogenic', conditions='Example',
        review_status='reviewed by expert panel', last_evaluated='')])
    results, stats = analyze_variants_with_stats(parse_vcf(str(path)), db)
    if copies == 0:
        assert results == [] and stats.reference_genotype_sites == 1
    else:
        result, = results
        assert result.alt_copies == copies
        assert not result.strand_flipped
        if copies is None:
            assert result.zygosity == 'unknown'
            assert stats.zygosity_unknown_sites == 1


@pytest.mark.parametrize('indices,alleles', [((2,), ('G',)), ((1,), ('A',)), ((0, 1, 1), ('A', 'G', 'G'))])
def test_inconsistent_structured_evidence_abstains(indices, alleles):
    from allelio.parsers.base import VCFEvidence
    from allelio.analysis.zygosity import call_vcf_zygosity
    evidence = VCFEvidence('A', ('G',), indices, alleles, False)
    assert call_vcf_zygosity(evidence, 'A', 'G').alt_copies is None
