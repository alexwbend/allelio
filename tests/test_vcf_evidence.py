"""Preserve source evidence independently of the legacy genotype display."""
import gzip
import pytest
from allelio.parsers.base import Variant
from allelio.parsers.vcf_parser import parse_vcf


def write_vcf(tmp_path, row, meta='', compressed=False):
    text = ('##fileformat=VCFv4.3\n' + meta +
            '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS\n' + row + '\n')
    path = tmp_path / ('case.vcf.gz' if compressed else 'case.vcf')
    if compressed:
        with gzip.open(path, 'wt') as stream:
            stream.write(text)
    else:
        path.write_text(text)
    return str(path)


@pytest.mark.parametrize('compressed', [False, True])
def test_multiallelic_phase_and_quality_preserved(tmp_path, compressed):
    path = write_vcf(tmp_path,
        '1\t100\trs1\tA\tG,AT\t42.5\tq10\t.\tGT:PS:GQ:DP\t2|1:100:0:12',
        '##reference=file:///reference/GRCh38.fa\n', compressed)
    variant, = parse_vcf(path)
    e = variant.vcf_evidence
    assert e.alleles == ('AT', 'G')
    assert e.allele_indices == (2, 1)
    assert e.reference == 'A' and e.alternates == ('G', 'AT')
    assert e.phased is True and e.ploidy == 2 and e.phase_set == '100'
    assert e.reference_declaration == 'file:///reference/GRCh38.fa'
    assert (e.quality, e.filter_status, e.genotype_quality, e.depth) == ('42.5', 'q10', '0', '12')


@pytest.mark.parametrize('gt,phased,ploidy', [('1', None, 1), ('0/1', False, 2)])
def test_missing_metadata_is_unknown(tmp_path, gt, phased, ploidy):
    v, = parse_vcf(write_vcf(tmp_path, f'X\t100\trs1\tA\tG\t.\t.\t.\tGT:GQ:DP\t{gt}:.:.'))
    e = v.vcf_evidence
    assert e.phased is phased and e.ploidy == ploidy
    assert e.reference_declaration is None
    assert e.quality is None and e.filter_status is None
    assert e.genotype_quality is None and e.depth is None and e.phase_set is None


def test_old_constructor_remains_compatible():
    assert Variant('rs1', '1', 100, 'AG').vcf_evidence is None


def test_invalid_header_does_not_crash(tmp_path):
    p = tmp_path / 'bad.vcf'
    p.write_text('##fileformat=VCFv4.3\n#CHROM\tPOS\n1\t100\n')
    assert parse_vcf(str(p)) == []


@pytest.mark.parametrize('gt', ['.', './.', '0/.', '3/0', '-1/0', '0/1/1', '0|1/0'])
def test_unsupported_or_missing_calls_stay_excluded(tmp_path, gt):
    assert parse_vcf(write_vcf(tmp_path, f'1\t100\trs1\tA\tG\t.\tPASS\t.\tGT\t{gt}')) == []


def test_haploid_multibase_allele_is_not_two_snp_copies(tmp_path):
    from allelio.analysis.zygosity import call_zygosity
    v, = parse_vcf(write_vcf(tmp_path, 'X\t100\trs1\tA\tAG\t.\tPASS\t.\tGT\t1'))
    assert v.vcf_evidence.alleles == ('AG',)
    assert v.vcf_evidence.ploidy == 1
    assert call_zygosity(v.genotype, 'A', 'G').alt_copies is None
