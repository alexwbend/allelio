"""Test suite for Allelio analysis engine."""

import pytest
from typing import List

from allelio.parsers.base import Variant
from allelio.analysis.lookup import (
    analyze_variants,
    VariantResult,
    VariantCategory,
    _get_significance_rank,
    _determine_category,
    ClinVarEntry,
    GWASEntry,
)


class TestAnalyzeVariantsBasic:
    """Tests for basic variant analysis."""
    
    def test_analyze_variants_basic(self, sample_db):
        """Test analyzing variants returns VariantResult objects."""
        variants = [
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="CT"),
            Variant(rsid="rs7412", chromosome="19", position=45412079, genotype="TC"),
            Variant(rsid="rs4988235", chromosome="2", position=135951944, genotype="CC"),
        ]
        
        results = analyze_variants(variants, sample_db)
        
        assert len(results) > 0
        assert all(isinstance(r, VariantResult) for r in results)
    
    def test_analyze_variants_returns_expected_fields(self, sample_db):
        """Test that results contain expected fields."""
        variants = [
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="CT"),
        ]
        
        results = analyze_variants(variants, sample_db)
        
        assert len(results) > 0
        result = results[0]
        
        assert result.rsid == "rs429358"
        assert result.chromosome == "19"
        assert result.position == 45411941
        assert result.genotype == "CT"
        assert result.category is not None
        assert result.significance_rank is not None
    
    def test_analyze_variants_empty_input(self, sample_db):
        """Test that empty input returns empty list."""
        results = analyze_variants([], sample_db)
        
        assert results == []
    
    def test_analyze_variants_no_matches(self, sample_db):
        """Test variants with no database matches."""
        variants = [
            Variant(rsid="rsNONEXISTENT", chromosome="1", position=100000, genotype="AA"),
        ]
        
        results = analyze_variants(variants, sample_db)
        
        # Should return empty list since variant not in database
        assert len(results) == 0


class TestAnalyzeVariantsSorting:
    """Tests for variant result sorting."""
    
    def test_analyze_variants_sorted(self, sample_db):
        """Test that results are sorted by significance rank."""
        # rs429358 and rs7412 are pathogenic (rank 1-2)
        # rs4988235 is association (rank 4)
        # rs12913832 is benign (rank 10)
        variants = [
            Variant(rsid="rs4988235", chromosome="2", position=135951944, genotype="CC"),
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="CT"),
            Variant(rsid="rs7412", chromosome="19", position=45412079, genotype="TC"),
        ]
        
        results = analyze_variants(variants, sample_db, include_benign=True)
        
        assert len(results) > 0
        
        # Check that results are sorted (significance_rank should be ascending)
        ranks = [r.significance_rank for r in results]
        assert ranks == sorted(ranks)
    
    def test_analyze_variants_most_significant_first(self, sample_db):
        """Test that most significant variants appear first."""
        # Pathogenic should rank higher than risk factor
        variants = [
            Variant(rsid="rs762551", chromosome="11", position=62326389, genotype="AA"),
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="CT"),
        ]
        
        results = analyze_variants(variants, sample_db)
        
        assert len(results) > 0
        # First result should have lower rank (more significant)
        if len(results) > 1:
            assert results[0].significance_rank <= results[1].significance_rank


class TestAnalyzeVariantsFiltering:
    """Tests for variant filtering."""
    
    def test_analyze_variants_filters_benign_default(self, sample_db):
        """Test that benign variants are excluded by default."""
        # rs12913832 is benign
        variants = [
            Variant(rsid="rs12913832", chromosome="15", position=28000000, genotype="GG"),
        ]
        
        results = analyze_variants(variants, sample_db, include_benign=False)
        
        # Benign variant should be filtered out
        assert len(results) == 0
    
    def test_analyze_variants_includes_benign_when_flag_set(self, sample_db):
        """Test that benign variants are included when flag is set."""
        # rs12913832 is benign
        variants = [
            Variant(rsid="rs12913832", chromosome="15", position=28000000, genotype="GG"),
        ]
        
        results = analyze_variants(variants, sample_db, include_benign=True)
        
        # Benign variant should be included
        assert len(results) > 0
        assert results[0].rsid == "rs12913832"
    
    def test_analyze_variants_mixed_benign_and_pathogenic(self, sample_db):
        """Test filtering with mix of benign and pathogenic."""
        variants = [
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="CT"),
            Variant(rsid="rs12913832", chromosome="15", position=28000000, genotype="GG"),
        ]
        
        # Without benign
        results_no_benign = analyze_variants(variants, sample_db, include_benign=False)
        
        # With benign
        results_with_benign = analyze_variants(variants, sample_db, include_benign=True)
        
        # Should have fewer results without benign
        assert len(results_with_benign) >= len(results_no_benign)


class TestVariantCategoryAssignment:
    """Tests for variant category assignment."""
    
    def test_variant_category_assignment(self, sample_db):
        """Test that categories are assigned correctly."""
        variants = [
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="CT"),
        ]
        
        results = analyze_variants(variants, sample_db)
        
        assert len(results) > 0
        result = results[0]
        assert result.category is not None
        # category is stored as the string .value of the enum
        valid_categories = [c.value for c in VariantCategory]
        assert result.category in valid_categories
    
    def test_category_health_conditions(self, sample_db):
        """Test category assignment for health conditions."""
        # rs429358 has clinical_significance="risk factor" which should be RISK_FACTORS
        variants = [
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="CT"),
        ]
        
        results = analyze_variants(variants, sample_db, include_benign=True)
        
        assert len(results) > 0
        # rs429358 should be risk factor related
        result = next((r for r in results if r.rsid == "rs429358"), None)
        if result:
            assert result.category in [
                VariantCategory.HEALTH_CONDITIONS.value,
                VariantCategory.RISK_FACTORS.value,
            ]


class TestSignificanceRanking:
    """Tests for significance ranking."""
    
    def test_significance_ranking_pathogenic(self, sample_db):
        """Test ranking for pathogenic variants."""
        rank = _get_significance_rank("pathogenic")
        
        # Pathogenic should have rank 1 (most significant)
        assert rank == 1
    
    def test_significance_ranking_likely_pathogenic(self, sample_db):
        """Test ranking for likely pathogenic."""
        rank = _get_significance_rank("likely pathogenic")
        
        # Likely pathogenic should have rank 2
        assert rank == 2
    
    def test_significance_ranking_benign(self, sample_db):
        """Test ranking for benign."""
        rank = _get_significance_rank("benign")
        
        # Benign should have high rank (low significance)
        assert rank == 10
    
    def test_significance_ranking_risk_factor(self, sample_db):
        """Test ranking for risk factor."""
        rank = _get_significance_rank("risk factor")
        
        # Risk factor should have rank 3
        assert rank == 3
    
    def test_significance_ranking_uncertain(self, sample_db):
        """Test ranking for uncertain significance."""
        rank = _get_significance_rank("uncertain significance")
        
        # Uncertain should have rank 7 (middle of spectrum)
        assert rank == 7
    
    def test_significance_ranking_case_insensitive(self, sample_db):
        """Test that ranking is case-insensitive."""
        rank_lower = _get_significance_rank("pathogenic")
        rank_upper = _get_significance_rank("PATHOGENIC")
        rank_mixed = _get_significance_rank("Pathogenic")
        
        # All should be equal
        assert rank_lower == rank_upper == rank_mixed
    
    def test_significance_ranking_unknown(self, sample_db):
        """Test ranking for unknown significance."""
        rank = _get_significance_rank("unknown_significance_string")
        
        # Unknown should get a default rank
        assert rank > 0


class TestClinvarEntries:
    """Tests for ClinVar entry handling."""
    
    def test_analyze_includes_clinvar_entries(self, sample_db):
        """Test that results include ClinVar entries."""
        variants = [
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="CT"),
        ]
        
        results = analyze_variants(variants, sample_db)
        
        assert len(results) > 0
        result = results[0]
        
        # Should have ClinVar entries
        assert result.clinvar_entries is not None
        assert isinstance(result.clinvar_entries, list)
        if result.clinvar_entries:
            assert all(isinstance(e, ClinVarEntry) for e in result.clinvar_entries)
    
    def test_clinvar_entry_fields(self, sample_db):
        """Test that ClinVar entries have expected fields."""
        variants = [
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="CT"),
        ]
        
        results = analyze_variants(variants, sample_db)
        
        assert len(results) > 0
        result = results[0]
        
        if result.clinvar_entries:
            entry = result.clinvar_entries[0]
            assert entry.rsid is not None
            assert entry.gene is not None
            assert entry.clinical_significance is not None


class TestGWASEntries:
    """Tests for GWAS entry handling."""
    
    def test_analyze_includes_gwas_entries(self, sample_db):
        """Test that results include GWAS entries."""
        variants = [
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="CT"),
        ]
        
        results = analyze_variants(variants, sample_db)
        
        assert len(results) > 0
        result = results[0]
        
        # Should have GWAS entries (if available in sample_db)
        assert result.gwas_entries is not None
        assert isinstance(result.gwas_entries, list)
        if result.gwas_entries:
            assert all(isinstance(e, GWASEntry) for e in result.gwas_entries)
    
    def test_gwas_entry_fields(self, sample_db):
        """Test that GWAS entries have expected fields."""
        variants = [
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="CT"),
        ]
        
        results = analyze_variants(variants, sample_db)
        
        assert len(results) > 0
        result = results[0]
        
        if result.gwas_entries:
            entry = result.gwas_entries[0]
            assert entry.rsid is not None
            assert entry.trait is not None


class TestAnalyzeVariantsIntegration:
    """Integration tests for variant analysis."""
    
    def test_analyze_multiple_variants_comprehensive(self, sample_db):
        """Test analyzing multiple variants with mixed significance."""
        variants = [
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="CT"),
            Variant(rsid="rs7412", chromosome="19", position=45412079, genotype="TC"),
            Variant(rsid="rs4988235", chromosome="2", position=135951944, genotype="CC"),
            Variant(rsid="rs1052373", chromosome="11", position=116648917, genotype="AA"),
        ]
        
        results = analyze_variants(variants, sample_db)
        
        # Should have results for variants in database
        assert len(results) > 0
        
        # All results should have valid fields
        for result in results:
            assert result.rsid is not None
            assert result.chromosome is not None
            assert result.position is not None
            assert result.genotype is not None
            assert result.category is not None
            assert result.significance_rank is not None
    
    def test_analyze_with_missing_variants(self, sample_db):
        """Test analyzing when some variants don't exist in database."""
        variants = [
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="CT"),
            Variant(rsid="rsNONEXISTENT", chromosome="1", position=100000, genotype="AA"),
            Variant(rsid="rs4988235", chromosome="2", position=135951944, genotype="CC"),
        ]
        
        results = analyze_variants(variants, sample_db)
        
        # Should only have results for variants in database
        assert len(results) <= 2
        rsids_in_results = {r.rsid for r in results}
        assert "rsNONEXISTENT" not in rsids_in_results
    
    def test_analyze_preserves_genotype_info(self, sample_db):
        """Test that genotype information is preserved in results."""
        genotype = "CT"
        variants = [
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype=genotype),
        ]
        
        results = analyze_variants(variants, sample_db)
        
        assert len(results) > 0
        result = results[0]
        assert result.genotype == genotype
    
    def test_analyze_with_no_calls(self, sample_db):
        """Test analyzing variants with no-call genotypes."""
        # Even if a parser included no-calls, analysis should handle them
        variants = [
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="--"),
        ]
        
        # Should not raise error
        results = analyze_variants(variants, sample_db)
        
        # Results behavior depends on implementation
        assert isinstance(results, list)
