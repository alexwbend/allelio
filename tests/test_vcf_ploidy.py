"""VCF-to-interpretation regression: do not manufacture a second allele."""
import pytest
from allelio.parsers.vcf_parser import parse_vcf
from allelio.analysis.zygosity import call_zygosity, Zygosity


@pytest.mark.parametrize("gt,genotype,copies,zygosity", [
    ("1", "G", 1, Zygosity.HEMIZYGOUS_ALTERNATE),
    ("0", "A", 0, Zygosity.HEMIZYGOUS_REFERENCE),
    ("0/1", "AG", 1, Zygosity.HETEROZYGOUS),
    ("1|1", "GG", 2, Zygosity.HOMOZYGOUS_ALTERNATE),
])
def test_vcf_reported_ploidy_reaches_interpretation(tmp_path, gt, genotype, copies, zygosity):
    path = tmp_path / "sample.vcf"
    path.write_text("##fileformat=VCFv4.2\n"
                    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n"
                    f"X\t100\trs900000001\tA\tG\t.\tPASS\t.\tGT\t{gt}\n")
    variants = parse_vcf(str(path))
    assert len(variants) == 1
    assert variants[0].genotype == genotype
    call = call_zygosity(variants[0].genotype, "A", "G")
    assert call.alt_copies == copies
    assert call.zygosity == zygosity
