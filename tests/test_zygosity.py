"""Zygosity: matching a genotype against the allele a database row describes.

The pure calls in allelio/analysis/zygosity.py, then the analysis step's use
of them: a ClinVar entry at a site where the person carries only the reference
allele is not a finding for them, and a heterozygous match is reported as one
copy, not as the same thing as two.
"""

from pathlib import Path

import pytest

from allelio.analysis.lookup import (
    AnalysisStats,
    analyze_variants,
    analyze_variants_with_stats,
)
from allelio.analysis.zygosity import Zygosity, call_zygosity, genotype_alleles
from allelio.database.clinvar import parse_clinvar
from allelio.database.gwas import parse_risk_allele
from allelio.database.store import AllelioDB
from allelio.parsers.base import Variant


class TestGenotypeAlleles:
    @pytest.mark.parametrize("g,expected", [
        ("AG", ["A", "G"]), ("A", ["A"]), ("DI", ["D", "I"]), ("ag", ["A", "G"]),
        ("--", []), ("00", []), ("", []), (None, []), ("AGT", []), ("A/G", []),
    ])
    def test_split(self, g, expected):
        assert genotype_alleles(g) == expected


class TestCallZygosity:
    def test_heterozygous(self):
        c = call_zygosity("AG", "A", "G")
        assert c.zygosity == Zygosity.HETEROZYGOUS and c.alt_copies == 1 and c.allele == "G"

    def test_homozygous_alternate(self):
        assert call_zygosity("GG", "A", "G").alt_copies == 2

    def test_homozygous_reference_is_zero_copies(self):
        c = call_zygosity("AA", "A", "G")
        assert c.zygosity == Zygosity.HOMOZYGOUS_REFERENCE and c.alt_copies == 0
        assert c.carries_allele is False

    def test_genotype_order_does_not_matter(self):
        assert call_zygosity("GA", "A", "G").alt_copies == 1

    def test_hemizygous(self):
        assert call_zygosity("G", "A", "G").zygosity == Zygosity.HEMIZYGOUS_ALTERNATE
        assert call_zygosity("A", "A", "G").zygosity == Zygosity.HEMIZYGOUS_REFERENCE

    def test_no_call(self):
        c = call_zygosity("--", "A", "G")
        assert c.zygosity == Zygosity.NO_CALL and c.alt_copies is None

    def test_missing_alt_is_unknown(self):
        assert call_zygosity("AG", "A", "").zygosity == Zygosity.UNKNOWN
        assert call_zygosity("AG", None, None).zygosity == Zygosity.UNKNOWN

    def test_ref_equals_alt_is_unknown(self):
        # ClinVar emits such rows for haplotype-level records.
        assert call_zygosity("TT", "T", "T").zygosity == Zygosity.UNKNOWN

    def test_opposite_strand_is_detected_and_flagged(self):
        c = call_zygosity("CT", "A", "G")  # complement of AG
        assert c.alt_copies == 1 and c.strand_flipped is True
        assert "opposite strand" in c.describe()

    def test_strand_ambiguous_site_does_not_flip(self):
        # A/T: "AT" matches directly; "TA" too. A mismatch cannot be repaired.
        assert call_zygosity("AT", "A", "T").alt_copies == 1
        assert call_zygosity("CG", "A", "T").zygosity == Zygosity.UNKNOWN

    def test_complemented_homozygous_alt_is_two_copies_flagged(self):
        c = call_zygosity("CC", "A", "G")
        # CC is GG on the other strand; A/G is not self-complementary, so the
        # flip is detectable and the call is made, with the flag set.
        assert c.alt_copies == 2 and c.strand_flipped is True

    def test_unmatchable_genotype_is_unknown_not_zero(self):
        c = call_zygosity("AC", "A", "G")
        assert c.zygosity == Zygosity.UNKNOWN and c.alt_copies is None

    def test_indels_from_23andme(self):
        assert call_zygosity("II", "A", "AT").alt_copies == 2
        assert call_zygosity("DI", "AT", "A").alt_copies == 1
        assert call_zygosity("DD", "A", "AT").alt_copies == 0

    def test_risk_allele_only_counts_when_present(self):
        assert call_zygosity("AG", None, "G").alt_copies == 1
        assert call_zygosity("AA", None, "G").alt_copies == 0

    def test_risk_allele_only_complement_present_is_unknown(self):
        assert call_zygosity("CC", None, "G").zygosity == Zygosity.UNKNOWN

    def test_describe(self):
        assert call_zygosity("AG", "A", "G").describe() == "heterozygous (1 copy of the G allele)"
        assert call_zygosity("GG", "A", "G").describe() == "homozygous alternate (2 copies of the G allele)"
        assert call_zygosity("--", "A", "G").describe() == "no call"


class TestParsers:
    def test_gwas_risk_allele(self):
        assert parse_risk_allele("rs6025-T") == "T"
        assert parse_risk_allele("rs6025-?") is None
        assert parse_risk_allele("") is None
        assert parse_risk_allele("rs1-A; rs2-G") is None
        assert parse_risk_allele("rs1-A x rs2-G") is None

    def test_clinvar_alleles_from_vcf_columns(self, tmp_path):
        header = (Path(__file__).parent / "fixtures/clinvar_context/variant_summary_unsplit.tsv").read_text().splitlines()[0]
        def row(rs, sig, ref, alt):
            r = ["0"] * 34
            r[4] = "HBB"; r[6] = sig; r[9] = rs; r[16] = "GRCh38"; r[24] = "criteria provided, single submitter"
            r[32] = ref; r[33] = alt
            return "\t".join(r)
        f = tmp_path / "cv.txt"
        f.write_text(header + "\n" + row("334", "Pathogenic", "T", "A") + "\n" + row("334", "Likely benign", "T", "G") + "\n" + row("999", "Pathogenic", "na", "na") + "\n")
        recs = list(parse_clinvar(str(f)))
        assert [(r["rsid"], r["ref_allele"], r["alt_allele"]) for r in recs] == [
            ("rs334", "T", "A"), ("rs334", "T", "G"), ("rs999", "", ""),
        ]


@pytest.fixture
def allele_db(tmp_path):
    db = AllelioDB(str(tmp_path / "a.db"))
    db.initialize()
    db.insert_clinvar_batch([
        # HBB rs334: T>A is sickle-cell (pathogenic), T>G is likely benign.
        {"rsid": "rs334", "ref_allele": "T", "alt_allele": "A", "gene": "HBB",
         "clinical_significance": "Pathogenic", "conditions": "Sickle cell anemia",
         "review_status": "reviewed by expert panel", "last_evaluated": ""},
        {"rsid": "rs334", "ref_allele": "T", "alt_allele": "G", "gene": "HBB",
         "clinical_significance": "Likely benign", "conditions": "not provided",
         "review_status": "criteria provided, single submitter", "last_evaluated": ""},
        # HFE C282Y rs1800562 G>A pathogenic
        {"rsid": "rs1800562", "ref_allele": "G", "alt_allele": "A", "gene": "HFE",
         "clinical_significance": "Pathogenic", "conditions": "Hemochromatosis",
         "review_status": "practice guideline", "last_evaluated": ""},
        # A row with no alleles recorded (legacy behaviour: kept, zygosity unknown)
        {"rsid": "rs111", "gene": "GENEX", "clinical_significance": "Pathogenic",
         "conditions": "Something", "review_status": "criteria provided, single submitter", "last_evaluated": ""},
    ])
    db.insert_gwas_batch([
        {"rsid": "rs222", "trait": "Height", "p_value": 1e-9, "odds_ratio": "1.1",
         "mapped_gene": "G2", "study": "S", "pubmed_id": "1", "link": "", "risk_allele": "C"},
        {"rsid": "rs333", "trait": "Weight", "p_value": 1e-9, "odds_ratio": "1.1",
         "mapped_gene": "G3", "study": "S", "pubmed_id": "1", "link": ""},
    ])
    return db


class TestAnalysisUsesAlleles:
    def test_reference_genotype_is_not_a_finding(self, allele_db):
        results, stats = analyze_variants_with_stats(
            [Variant("rs1800562", "6", 26093141, "GG")], allele_db
        )
        assert results == []
        assert stats.annotated_sites == 1 and stats.reference_genotype_sites == 1

    def test_heterozygous_is_one_copy(self, allele_db):
        [r] = analyze_variants([Variant("rs1800562", "6", 26093141, "AG")], allele_db)
        assert r.zygosity == "heterozygous" and r.alt_copies == 1 and r.matched_allele == "A"
        assert r.describe_zygosity() == "heterozygous (1 copy of the A allele)"

    def test_homozygous_alternate_is_two_copies(self, allele_db):
        [r] = analyze_variants([Variant("rs1800562", "6", 26093141, "AA")], allele_db)
        assert r.zygosity == "homozygous alternate" and r.alt_copies == 2

    def test_picks_the_allele_the_person_carries(self, allele_db):
        # Carrying the G allele at rs334 is the likely-benign row, not sickle cell.
        results = analyze_variants([Variant("rs334", "11", 5227002, "TG")], allele_db, include_benign=True)
        assert len(results) == 1
        assert results[0].clinvar_entries[0].clinical_significance == "Likely benign"
        assert results[0].matched_allele == "G"

    def test_carrying_the_pathogenic_allele_is_reported_as_such(self, allele_db):
        [r] = analyze_variants([Variant("rs334", "11", 5227002, "AT")], allele_db)
        assert r.clinvar_entries[0].clinical_significance == "Pathogenic"
        assert r.category == "Health Conditions" and r.alt_copies == 1

    def test_rows_without_alleles_are_kept_with_unknown_zygosity(self, allele_db):
        [r], stats = analyze_variants_with_stats([Variant("rs111", "1", 1, "AG")], allele_db)
        assert r.zygosity == "unknown" and r.alt_copies is None
        assert stats.zygosity_unknown_sites == 1

    def test_gwas_risk_allele_absent_is_set_aside(self, allele_db):
        results, stats = analyze_variants_with_stats([Variant("rs222", "1", 1, "AA")], allele_db)
        assert results == [] and stats.reference_genotype_sites == 1

    def test_gwas_risk_allele_present_is_counted(self, allele_db):
        [r] = analyze_variants([Variant("rs222", "1", 1, "AC")], allele_db)
        assert r.alt_copies == 1 and r.matched_allele == "C"

    def test_gwas_without_risk_allele_is_unknown_not_dropped(self, allele_db):
        [r] = analyze_variants([Variant("rs333", "1", 1, "AA")], allele_db)
        assert r.zygosity == "unknown"

    def test_include_reference_keeps_them(self, allele_db):
        [r] = analyze_variants([Variant("rs1800562", "6", 26093141, "GG")], allele_db, include_reference=True)
        assert r.zygosity == "homozygous reference" and r.alt_copies == 0

    def test_no_call_genotype(self, allele_db):
        [r] = analyze_variants([Variant("rs1800562", "6", 26093141, "--")], allele_db)
        assert r.zygosity == "no call"


class TestSchemaMigration:
    def test_old_clinvar_table_is_rebuilt_and_reads_uninitialized(self, tmp_path):
        db = AllelioDB(str(tmp_path / "old.db"))
        db.cursor.execute("CREATE TABLE clinvar (rsid TEXT PRIMARY KEY, gene TEXT, clinical_significance TEXT, conditions TEXT, review_status TEXT, last_evaluated TEXT)")
        db.cursor.execute("INSERT INTO clinvar VALUES ('rs1','G','Pathogenic','c','r','d')")
        db.conn.commit()
        assert db.clinvar_is_allele_aware() is False
        assert db.is_initialized() is False  # points the user at allelio setup
        db.initialize()
        assert db.clinvar_is_allele_aware() is True
        db.cursor.execute("SELECT COUNT(*) FROM clinvar")
        assert db.cursor.fetchone()[0] == 0

    def test_old_gwas_table_gains_risk_allele_column(self, tmp_path):
        db = AllelioDB(str(tmp_path / "old.db"))
        db.cursor.execute("CREATE TABLE gwas (id INTEGER PRIMARY KEY AUTOINCREMENT, rsid TEXT NOT NULL, trait TEXT, p_value REAL, odds_ratio TEXT, mapped_gene TEXT, study TEXT, pubmed_id TEXT, link TEXT)")
        db.conn.commit()
        db.initialize()
        assert "risk_allele" in db._columns("gwas")

    def test_same_rsid_different_alleles_both_kept(self, allele_db):
        rows = allele_db.lookup_rsid("rs334")["clinvar"]
        assert sorted(r["alt_allele"] for r in rows) == ["A", "G"]
