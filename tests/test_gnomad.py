"""Tests for gnomAD population frequency integration."""

import pytest
from pathlib import Path

from allelio.database.gnomad import parse_gnomad
from allelio.database.store import AllelioDB
from allelio.analysis.lookup import (
    GnomADEntry,
    VariantResult,
    _calculate_frequency_adjustment,
    analyze_variants,
)
from allelio.ai.prompts import format_gnomad_summary, build_variant_prompt
from allelio.parsers.base import Variant


# ── Parser Tests ──────────────────────────────────────────────────────


class TestGnomADParser:
    """Tests for gnomAD TSV file parsing."""

    def test_parse_basic_tsv(self, tmp_dir):
        """Test parsing a well-formed gnomAD TSV file."""
        file_path = Path(tmp_dir) / "gnomad_test.tsv"
        content = (
            "rsid\tallele_frequency\taf_popmax\tac\tan\tnhomalt\n"
            "rs429358\t0.0523\t0.0789\t98765\t1890000\t12345\n"
            "rs7412\t0.0742\t0.1200\t140000\t1890000\t18900\n"
            "rs1234\t0.00001\t0.00005\t5\t500000\t0\n"
        )
        file_path.write_text(content)

        records = list(parse_gnomad(str(file_path)))

        assert len(records) == 3
        assert records[0]["rsid"] == "rs429358"
        assert records[0]["allele_frequency"] == pytest.approx(0.0523)
        assert records[0]["af_popmax"] == pytest.approx(0.0789)
        assert records[0]["ac"] == 98765
        assert records[0]["an"] == 1890000
        assert records[0]["nhomalt"] == 12345

    def test_parse_skips_invalid_rsids(self, tmp_dir):
        """Test that lines without valid rsIDs are skipped."""
        file_path = Path(tmp_dir) / "gnomad_test.tsv"
        content = (
            "rsid\tallele_frequency\n"
            "rs429358\t0.05\n"
            ".\t0.10\n"
            "-\t0.20\n"
            "chr1:12345\t0.30\n"
            "rs7412\t0.07\n"
        )
        file_path.write_text(content)

        records = list(parse_gnomad(str(file_path)))

        assert len(records) == 2
        assert records[0]["rsid"] == "rs429358"
        assert records[1]["rsid"] == "rs7412"

    def test_parse_handles_missing_values(self, tmp_dir):
        """Test graceful handling of missing or NA values."""
        file_path = Path(tmp_dir) / "gnomad_test.tsv"
        content = (
            "rsid\tallele_frequency\taf_popmax\tac\tan\tnhomalt\n"
            "rs429358\t0.05\tNA\t-\t.\t\n"
        )
        file_path.write_text(content)

        records = list(parse_gnomad(str(file_path)))

        assert len(records) == 1
        assert records[0]["rsid"] == "rs429358"
        assert records[0]["allele_frequency"] == pytest.approx(0.05)
        assert records[0]["af_popmax"] is None
        assert records[0]["ac"] is None
        assert records[0]["an"] is None
        assert records[0]["nhomalt"] is None

    def test_parse_skips_comment_lines(self, tmp_dir):
        """Test that comment lines starting with ## are skipped."""
        file_path = Path(tmp_dir) / "gnomad_test.tsv"
        content = (
            "## gnomAD v4.1 allele frequencies\n"
            "## Generated 2026-01-15\n"
            "rsid\tallele_frequency\n"
            "rs429358\t0.05\n"
        )
        file_path.write_text(content)

        records = list(parse_gnomad(str(file_path)))
        assert len(records) == 1

    def test_parse_empty_file(self, tmp_dir):
        """Test parsing an empty file."""
        file_path = Path(tmp_dir) / "empty.tsv"
        file_path.write_text("")

        records = list(parse_gnomad(str(file_path)))
        assert len(records) == 0

    def test_parse_grpmax_alias(self, tmp_dir):
        """Test that AF_grpmax (v4 naming) maps to af_popmax."""
        file_path = Path(tmp_dir) / "gnomad_v4.tsv"
        content = (
            "rsid\tAF\tAF_grpmax\tAC\tAN\tnhomalt\tAF_afr\tAF_eas\tAF_fin\tAF_nfe\tAF_sas\n"
            "rs429358\t0.0523\t0.0789\t98765\t1890000\t12345\t0.03\t0.01\t0.06\t0.07\t0.04\n"
        )
        file_path.write_text(content)

        records = list(parse_gnomad(str(file_path)))

        assert len(records) == 1
        assert records[0]["rsid"] == "rs429358"
        assert records[0]["allele_frequency"] == pytest.approx(0.0523)
        # AF_grpmax should map to af_popmax
        assert records[0]["af_popmax"] == pytest.approx(0.0789)
        assert records[0]["af_afr"] == pytest.approx(0.03)
        assert records[0]["af_nfe"] == pytest.approx(0.07)

    def test_parse_rejects_out_of_range_af(self, tmp_dir):
        """Test that AF values outside 0-1 are rejected."""
        file_path = Path(tmp_dir) / "gnomad_test.tsv"
        content = (
            "rsid\tallele_frequency\n"
            "rs1\t0.05\n"
            "rs2\t-0.1\n"
            "rs3\t1.5\n"
            "rs4\t0.99\n"
        )
        file_path.write_text(content)

        records = list(parse_gnomad(str(file_path)))
        assert len(records) == 4
        assert records[0]["allele_frequency"] == pytest.approx(0.05)
        assert records[1]["allele_frequency"] is None  # negative
        assert records[2]["allele_frequency"] is None  # >1
        assert records[3]["allele_frequency"] == pytest.approx(0.99)


# ── Database Tests ────────────────────────────────────────────────────


class TestGnomADDatabase:
    """Tests for gnomAD database operations."""

    def test_insert_and_lookup_gnomad(self, tmp_dir):
        """Test inserting and looking up gnomAD records."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()

        records = [
            {
                "rsid": "rs429358",
                "allele_frequency": 0.0523,
                "af_popmax": 0.0789,
                "ac": 98765,
                "an": 1890000,
                "nhomalt": 12345,
                "af_afr": 0.03,
                "af_eas": 0.01,
                "af_fin": 0.06,
                "af_nfe": 0.07,
                "af_sas": 0.04,
            },
        ]
        db.insert_gnomad_batch(records)

        result = db.lookup_rsid("rs429358")
        assert result["gnomad"] is not None
        assert result["gnomad"]["allele_frequency"] == pytest.approx(0.0523)
        assert result["gnomad"]["af_popmax"] == pytest.approx(0.0789)

    def test_lookup_missing_gnomad(self, tmp_dir):
        """Test that missing gnomAD entries return None."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()

        result = db.lookup_rsid("rs999999")
        assert result["gnomad"] is None

    def test_batch_lookup_includes_gnomad(self, tmp_dir):
        """Test batch lookup returns gnomAD data alongside ClinVar/GWAS."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()

        # Insert gnomAD data
        db.insert_gnomad_batch([
            {"rsid": "rs429358", "allele_frequency": 0.05, "af_popmax": 0.08,
             "ac": None, "an": None, "nhomalt": None,
             "af_afr": None, "af_eas": None, "af_fin": None, "af_nfe": None, "af_sas": None},
            {"rsid": "rs7412", "allele_frequency": 0.07, "af_popmax": 0.12,
             "ac": None, "an": None, "nhomalt": None,
             "af_afr": None, "af_eas": None, "af_fin": None, "af_nfe": None, "af_sas": None},
        ])

        results = db.lookup_rsids_batch(["rs429358", "rs7412", "rs999"])

        assert results["rs429358"]["gnomad"] is not None
        assert results["rs429358"]["gnomad"]["allele_frequency"] == pytest.approx(0.05)
        assert results["rs7412"]["gnomad"] is not None
        assert results["rs999"]["gnomad"] is None

    def test_gnomad_stats(self, tmp_dir):
        """Test that get_stats includes gnomAD count."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()

        db.insert_gnomad_batch([
            {"rsid": "rs1", "allele_frequency": 0.01, "af_popmax": None,
             "ac": None, "an": None, "nhomalt": None,
             "af_afr": None, "af_eas": None, "af_fin": None, "af_nfe": None, "af_sas": None},
            {"rsid": "rs2", "allele_frequency": 0.02, "af_popmax": None,
             "ac": None, "an": None, "nhomalt": None,
             "af_afr": None, "af_eas": None, "af_fin": None, "af_nfe": None, "af_sas": None},
        ])

        stats = db.get_stats()
        assert stats["gnomad_entries"] == 2

    def test_backward_compat_no_gnomad_table(self, tmp_dir):
        """Test that lookups work on databases without gnomad table."""
        db_path = str(Path(tmp_dir) / "old.db")
        db = AllelioDB(db_path=db_path)
        # Only create clinvar and gwas tables (simulating old DB)
        db.cursor.execute("""
            CREATE TABLE IF NOT EXISTS clinvar (
                rsid TEXT PRIMARY KEY, gene TEXT,
                clinical_significance TEXT, conditions TEXT,
                review_status TEXT, last_evaluated TEXT)
        """)
        db.cursor.execute("""
            CREATE TABLE IF NOT EXISTS gwas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, rsid TEXT,
                trait TEXT, p_value REAL, odds_ratio TEXT,
                mapped_gene TEXT, study TEXT, pubmed_id TEXT, link TEXT)
        """)
        db.cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)
        """)
        db.conn.commit()

        # Should not crash, gnomad should be None
        result = db.lookup_rsid("rs123")
        assert result["gnomad"] is None

        batch = db.lookup_rsids_batch(["rs123"])
        assert batch["rs123"]["gnomad"] is None


# ── Frequency Adjustment Tests ────────────────────────────────────────


class TestFrequencyAdjustment:
    """Tests for _calculate_frequency_adjustment()."""

    def test_common_variant_downgraded(self):
        """Common variants (>5% AF) get a large rank increase."""
        entry = GnomADEntry(rsid="rs1", allele_frequency=0.30)
        adjusted = _calculate_frequency_adjustment(1.0, entry)
        assert adjusted == pytest.approx(4.0)  # 1.0 + 3.0

    def test_moderate_variant_downgraded(self):
        """Moderately common variants (1-5%) get moderate rank increase."""
        entry = GnomADEntry(rsid="rs1", allele_frequency=0.03)
        adjusted = _calculate_frequency_adjustment(1.0, entry)
        assert adjusted == pytest.approx(2.5)  # 1.0 + 1.5

    def test_uncommon_variant_small_downgrade(self):
        """Uncommon variants (0.1-1%) get small rank increase."""
        entry = GnomADEntry(rsid="rs1", allele_frequency=0.005)
        adjusted = _calculate_frequency_adjustment(1.0, entry)
        assert adjusted == pytest.approx(1.5)  # 1.0 + 0.5

    def test_rare_variant_unchanged(self):
        """Rare variants (<0.1%) keep their original rank."""
        entry = GnomADEntry(rsid="rs1", allele_frequency=0.0001)
        adjusted = _calculate_frequency_adjustment(1.0, entry)
        assert adjusted == pytest.approx(1.0)  # unchanged

    def test_very_rare_variant_unchanged(self):
        """Very rare variants (<0.001%) keep their original rank."""
        entry = GnomADEntry(rsid="rs1", allele_frequency=0.000001)
        adjusted = _calculate_frequency_adjustment(2.0, entry)
        assert adjusted == pytest.approx(2.0)

    def test_no_gnomad_data_unchanged(self):
        """Variants without gnomAD data keep their original rank."""
        adjusted = _calculate_frequency_adjustment(1.0, None)
        assert adjusted == pytest.approx(1.0)

    def test_no_frequency_unchanged(self):
        """Variants with gnomAD entry but no AF keep their original rank."""
        entry = GnomADEntry(rsid="rs1", allele_frequency=None)
        adjusted = _calculate_frequency_adjustment(1.0, entry)
        assert adjusted == pytest.approx(1.0)

    def test_rank_capped_at_9_9(self):
        """Adjustment should never push rank past 9.9."""
        entry = GnomADEntry(rsid="rs1", allele_frequency=0.50)
        adjusted = _calculate_frequency_adjustment(8.0, entry)
        assert adjusted == pytest.approx(9.9)  # capped, not 11.0

    def test_borderline_5_percent(self):
        """Test boundary at exactly 5%."""
        entry_above = GnomADEntry(rsid="rs1", allele_frequency=0.051)
        entry_below = GnomADEntry(rsid="rs2", allele_frequency=0.049)

        adj_above = _calculate_frequency_adjustment(1.0, entry_above)
        adj_below = _calculate_frequency_adjustment(1.0, entry_below)

        assert adj_above > adj_below  # Above 5% gets larger adjustment


# ── Analysis Integration Tests ────────────────────────────────────────


class TestAnalysisWithGnomAD:
    """Tests for analyze_variants with gnomAD data integrated."""

    def test_gnomad_entry_populated(self, sample_db_with_gnomad):
        """Test that analyzed variants include gnomAD frequency data."""
        variants = [
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="CT"),
        ]
        results = analyze_variants(variants, sample_db_with_gnomad)

        assert len(results) > 0
        result = results[0]
        assert result.gnomad_entry is not None
        assert result.gnomad_entry.allele_frequency == pytest.approx(0.0523)

    def test_gnomad_entry_none_when_missing(self, sample_db_with_gnomad):
        """Test that variants without gnomAD data have None entry."""
        # rs1052373 has GWAS data but no gnomAD in our fixture
        variants = [
            Variant(rsid="rs1052373", chromosome="11", position=116648917, genotype="AA"),
        ]
        results = analyze_variants(variants, sample_db_with_gnomad)

        if results:
            assert results[0].gnomad_entry is None

    def test_common_variant_rank_adjusted(self, sample_db_with_gnomad):
        """Test that common variants get a higher (less significant) rank."""
        # rs4988235 has AF=0.35 (common) in our fixture
        variants = [
            Variant(rsid="rs4988235", chromosome="2", position=135951944, genotype="CC"),
        ]
        results = analyze_variants(variants, sample_db_with_gnomad)

        assert len(results) > 0
        result = results[0]
        # Base rank for "association" is 4, should be bumped up by ~3.0
        assert result.significance_rank > 4.0

    def test_sorting_by_adjusted_rank(self, sample_db_with_gnomad):
        """Test that results are sorted by frequency-adjusted rank."""
        variants = [
            Variant(rsid="rs429358", chromosome="19", position=45411941, genotype="CT"),
            Variant(rsid="rs4988235", chromosome="2", position=135951944, genotype="CC"),
            Variant(rsid="rs762551", chromosome="11", position=62326389, genotype="AA"),
        ]
        results = analyze_variants(variants, sample_db_with_gnomad)

        ranks = [r.significance_rank for r in results]
        assert ranks == sorted(ranks)


# ── AI Prompt Tests ───────────────────────────────────────────────────


class TestGnomADPrompts:
    """Tests for gnomAD data in AI prompts."""

    def test_format_gnomad_summary_with_data(self):
        """Test formatting gnomAD data for prompt inclusion."""
        entry = GnomADEntry(
            rsid="rs429358",
            allele_frequency=0.0523,
            af_popmax=0.0789,
            ac=98765,
            an=1890000,
        )
        summary = format_gnomad_summary(entry)

        assert "5.2300%" in summary
        assert "98,765" in summary
        assert "Highest in any population" in summary

    def test_format_gnomad_summary_common(self):
        """Test that common variants get appropriate context."""
        entry = GnomADEntry(rsid="rs1", allele_frequency=0.35)
        summary = format_gnomad_summary(entry)

        assert "Common variant" in summary

    def test_format_gnomad_summary_rare(self):
        """Test that rare variants get appropriate context."""
        entry = GnomADEntry(rsid="rs1", allele_frequency=0.00005)
        summary = format_gnomad_summary(entry)

        assert "Rare variant" in summary

    def test_format_gnomad_summary_none(self):
        """Test formatting when no gnomAD data available."""
        summary = format_gnomad_summary(None)
        assert "No population frequency data" in summary

    def test_build_variant_prompt_includes_gnomad(self):
        """Test that build_variant_prompt includes gnomAD section."""
        from allelio.analysis.lookup import ClinVarEntry

        result = VariantResult(
            rsid="rs429358",
            chromosome="19",
            position=45411941,
            genotype="CT",
            clinvar_entries=[ClinVarEntry(
                rsid="rs429358", gene="APOE",
                clinical_significance="risk factor",
                conditions="Alzheimer disease",
            )],
            gnomad_entry=GnomADEntry(
                rsid="rs429358", allele_frequency=0.05,
            ),
        )
        prompt = build_variant_prompt(result)

        assert "Population Frequency" in prompt
        assert "5.0000%" in prompt
