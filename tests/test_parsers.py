"""Test suite for Allelio parsers."""

import pytest
from pathlib import Path

from allelio.parsers import detect_format, parse_genotype_file
from allelio.parsers.base import Variant


class TestFormatDetection:
    """Tests for format detection."""
    
    def test_detect_format_23andme(self, sample_23andme_file):
        """Test that 23andMe files are correctly detected."""
        fmt = detect_format(sample_23andme_file)
        assert fmt == "23andme"
    
    def test_detect_format_ancestry(self, sample_ancestry_file):
        """Test that AncestryDNA files are correctly detected."""
        fmt = detect_format(sample_ancestry_file)
        assert fmt == "ancestry"
    
    def test_detect_format_vcf(self, sample_vcf_file):
        """Test that VCF files are correctly detected."""
        fmt = detect_format(sample_vcf_file)
        assert fmt == "vcf"
    
    def test_detect_format_invalid(self, tmp_dir):
        """Test that invalid files raise ValueError."""
        invalid_file = Path(tmp_dir) / "invalid.txt"
        invalid_file.write_text("This is not a valid genotype file\nNo headers or data")
        
        with pytest.raises(ValueError):
            detect_format(str(invalid_file))
    
    def test_detect_format_nonexistent(self):
        """Test that nonexistent files raise appropriate error."""
        with pytest.raises((FileNotFoundError, ValueError)):
            detect_format("/nonexistent/file.txt")


class TestParse23andMe:
    """Tests for 23andMe format parsing."""
    
    def test_parse_23andme_basic(self, sample_23andme_file):
        """Test basic 23andMe parsing returns correct number of variants."""
        variants = parse_genotype_file(sample_23andme_file)

        # Should have 18 variants (20 data lines minus 2 no-calls with --)
        assert len(variants) == 18
        assert all(isinstance(v, Variant) for v in variants)
    
    def test_parse_23andme_no_nocalls(self, sample_23andme_file):
        """Test that no-calls (--) are filtered out."""
        variants = parse_genotype_file(sample_23andme_file)

        # No variants with -- genotype
        assert not any(v.genotype == "--" for v in variants)

        # Should be 18 after filtering (20 - 2 no-calls)
        assert len(variants) == 18
    
    def test_parse_23andme_variant_fields(self, sample_23andme_file):
        """Test that variant fields are correctly populated."""
        variants = parse_genotype_file(sample_23andme_file)
        
        # Find a specific variant
        rs429358 = next(v for v in variants if v.rsid == "rs429358")
        
        assert rs429358.rsid == "rs429358"
        assert rs429358.chromosome == "19"
        assert rs429358.position == 45411941
        assert rs429358.genotype == "CT"
    
    def test_parse_23andme_genotype_format(self, sample_23andme_file):
        """Test that genotypes are in correct format."""
        variants = parse_genotype_file(sample_23andme_file)
        
        for v in variants:
            # Each genotype should be 2 characters (one allele per chromosome)
            assert len(v.genotype) == 2
            # Each character should be a valid nucleotide
            assert all(c in "ACGT" for c in v.genotype)
    
    def test_parse_23andme_chromosome_values(self, sample_23andme_file):
        """Test that chromosome values are valid."""
        variants = parse_genotype_file(sample_23andme_file)
        
        valid_chromosomes = set(
            [str(i) for i in range(1, 23)] + ["X", "Y", "MT"]
        )
        
        for v in variants:
            assert v.chromosome in valid_chromosomes


class TestParseAncestry:
    """Tests for AncestryDNA format parsing."""
    
    def test_parse_ancestry_basic(self, sample_ancestry_file):
        """Test basic AncestryDNA parsing."""
        variants = parse_genotype_file(sample_ancestry_file)

        # Should have 18 variants (20 minus 2 no-calls)
        assert len(variants) == 18
        assert all(isinstance(v, Variant) for v in variants)
    
    def test_parse_ancestry_no_nocalls(self, sample_ancestry_file):
        """Test that no-calls (0/0) are filtered in AncestryDNA format."""
        variants = parse_genotype_file(sample_ancestry_file)
        
        # No variants with -- genotype
        assert not any(v.genotype == "--" for v in variants)
    
    def test_parse_ancestry_combines_alleles(self, sample_ancestry_file):
        """Test that allele1 and allele2 are combined into genotype."""
        variants = parse_genotype_file(sample_ancestry_file)
        
        # Find variant that has different alleles
        rs429358 = next(v for v in variants if v.rsid == "rs429358")
        
        # Should combine allele1 (C) and allele2 (T) into genotype
        assert rs429358.genotype == "CT"
        assert len(rs429358.genotype) == 2
    
    def test_parse_ancestry_same_alleles(self, sample_ancestry_file):
        """Test parsing of homozygous variants."""
        variants = parse_genotype_file(sample_ancestry_file)
        
        # Find homozygous variant
        rs1234 = next(v for v in variants if v.rsid == "rs1234")
        
        assert rs1234.genotype == "AA"
    
    def test_parse_ancestry_variant_fields(self, sample_ancestry_file):
        """Test that variant fields are correctly populated."""
        variants = parse_genotype_file(sample_ancestry_file)
        
        rs4988235 = next(v for v in variants if v.rsid == "rs4988235")
        
        assert rs4988235.rsid == "rs4988235"
        assert rs4988235.chromosome == "2"
        assert rs4988235.position == 135951944
        assert rs4988235.genotype == "CC"


class TestParseVCF:
    """Tests for VCF format parsing."""
    
    def test_parse_vcf_basic(self, sample_vcf_file):
        """Test basic VCF parsing."""
        variants = parse_genotype_file(sample_vcf_file)
        
        # Should have 10 variants from the VCF file
        assert len(variants) == 10
        assert all(isinstance(v, Variant) for v in variants)
    
    def test_parse_vcf_variant_fields(self, sample_vcf_file):
        """Test that VCF variant fields are correctly populated."""
        variants = parse_genotype_file(sample_vcf_file)
        
        rs429358 = next(v for v in variants if v.rsid == "rs429358")
        
        assert rs429358.rsid == "rs429358"
        assert rs429358.chromosome == "19"
        assert rs429358.position == 45411941
    
    def test_parse_vcf_genotype_conversion(self, sample_vcf_file):
        """Test that VCF GT field (0/1) is converted to alleles."""
        variants = parse_genotype_file(sample_vcf_file)
        
        # VCF format uses 0 for REF and 1 for ALT
        # 0/0 = REF/REF, 0/1 = REF/ALT, 1/1 = ALT/ALT
        
        # rs1234 has GT 0/0 (homozygous reference)
        rs1234 = next(v for v in variants if v.rsid == "rs1234")
        assert rs1234.genotype == "AA"  # REF is A, ALT is G, so 0/0 = AA
        
        # rs429358 has GT 0/1 (heterozygous)
        rs429358 = next(v for v in variants if v.rsid == "rs429358")
        assert rs429358.genotype == "CT"  # REF is C, ALT is T, so 0/1 = CT
    
    def test_parse_vcf_has_header(self, sample_vcf_file):
        """Test that VCF file with proper header is parsed correctly."""
        with open(sample_vcf_file) as f:
            first_line = f.readline()
        
        assert first_line.startswith("##fileformat=VCF")


class TestParseInvalidFile:
    """Tests for error handling."""
    
    def test_parse_invalid_file(self, tmp_dir):
        """Test that ValueError is raised for non-genotype files."""
        invalid_file = Path(tmp_dir) / "invalid.txt"
        invalid_file.write_text("This is not a valid genotype file\nNo proper format")
        
        with pytest.raises(ValueError):
            parse_genotype_file(str(invalid_file))
    
    def test_parse_nonexistent_file(self):
        """Test that FileNotFoundError is raised for missing files."""
        with pytest.raises(FileNotFoundError):
            parse_genotype_file("/nonexistent/file.txt")
    
    def test_parse_empty_file(self, tmp_dir):
        """Test that empty files raise appropriate error."""
        empty_file = Path(tmp_dir) / "empty.txt"
        empty_file.write_text("")
        
        with pytest.raises((ValueError, FileNotFoundError)):
            parse_genotype_file(str(empty_file))


class TestParserRobustness:
    """Tests for parser robustness with edge cases."""
    
    def test_parse_23andme_with_extra_whitespace(self, tmp_dir):
        """Test parsing 23andMe file with extra whitespace."""
        file_path = Path(tmp_dir) / "23andme_whitespace.txt"
        content = """# 23andMe format
rs1234\t1\t100000\tAA
rs429358\t19\t45411941\tCT  
rs7412\t19\t45412079\tTC
"""
        file_path.write_text(content)
        
        variants = parse_genotype_file(str(file_path))
        assert len(variants) >= 3
    
    def test_parse_multiple_formats_sequential(self, sample_23andme_file, sample_ancestry_file, sample_vcf_file):
        """Test parsing multiple files sequentially."""
        v23 = parse_genotype_file(sample_23andme_file)
        vAncestry = parse_genotype_file(sample_ancestry_file)
        vVCF = parse_genotype_file(sample_vcf_file)
        
        assert len(v23) > 0
        assert len(vAncestry) > 0
        assert len(vVCF) > 0
        
        # All should have variants
        assert all(isinstance(v, Variant) for v in v23 + vAncestry + vVCF)
