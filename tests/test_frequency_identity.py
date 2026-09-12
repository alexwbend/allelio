"""Population frequencies are matched by assembly, coordinate, and allele.

A gnomAD record may only be described as the matched allele's frequency, or
move a rank, when its identity agrees with the allele the person carries.
Everything else stays inspectable as context and says why it was not used.
All data here is synthetic.
"""

import gzip
import sys
from pathlib import Path

import pytest

from allelio.ai.prompts import format_gnomad_summary
from allelio.analysis.frequency import AlleleAnchor, frequency_identity
from allelio.analysis.lookup import (
    COMMON_AF_PENALTY, GnomADEntry, _calculate_frequency_adjustment, analyze_variants,
)
from allelio.database.gnomad import gnomad_file_header, parse_gnomad
from allelio.database.store import AllelioDB
from allelio.parsers.base import VCFEvidence, Variant
from allelio.report import generate_html_report

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_gnomad_freq import allele_values, emit_records, parse_info_field  # noqa: E402

ANCHOR = AlleleAnchor("GRCh38", "11", 5227002, "T", "A", "the matched ClinVar record")


def _record(**kwargs):
    base = dict(assembly="GRCh38", chromosome="11", position=5227002, ref_allele="T", alt_allele="A")
    base.update(kwargs)
    return base


class TestFrequencyIdentity:
    def test_matched(self):
        identity, note = frequency_identity(_record(), ANCHOR)
        assert identity == "matched" and "11:5227002 T>A" in note

    def test_missing_identity_is_unverified_with_refresh_hint(self):
        identity, note = frequency_identity(_record(ref_allele="", alt_allele=""), ANCHOR)
        assert identity == "unverified" and "allelio update" in note

    def test_no_anchor_is_unverified(self):
        assert frequency_identity(_record(), None)[0] == "unverified"

    def test_undeclared_assembly_is_unverified(self):
        identity, note = frequency_identity(_record(assembly=None), ANCHOR)
        assert identity == "unverified" and "assembly" in note

    def test_build_mismatch(self):
        identity, note = frequency_identity(_record(assembly="GRCh37"), ANCHOR)
        assert identity == "build_mismatch" and "GRCh37" in note and "GRCh38" in note

    def test_position_and_chromosome_mismatch(self):
        assert frequency_identity(_record(position=5227003), ANCHOR)[0] == "position_mismatch"
        assert frequency_identity(_record(chromosome="12"), ANCHOR)[0] == "position_mismatch"
        assert frequency_identity(_record(chromosome="chr11"), ANCHOR)[0] == "matched"

    def test_other_alternate_allele_at_multiallelic_site(self):
        identity, note = frequency_identity(_record(alt_allele="G"), ANCHOR)
        assert identity == "other_allele" and "T>G" in note and "T>A" in note

    def test_alleles_swapped(self):
        assert frequency_identity(_record(ref_allele="A", alt_allele="T"), ANCHOR)[0] == "alleles_swapped"

    def test_reversed_orientation_is_not_flipped(self):
        # At a T/A or C/G site the complement is also the swap, so it reads
        # as swapped; a C>T site read as G>A is unambiguously the other strand.
        identity, note = frequency_identity(_record(ref_allele="G", alt_allele="C"),
                                            AlleleAnchor("GRCh38", "11", 5227002, "C", "G", "x"))
        assert identity == "alleles_swapped"
        identity, note = frequency_identity(_record(ref_allele="G", alt_allele="A"),
                                            AlleleAnchor("GRCh38", "11", 5227002, "C", "T", "x"))
        assert identity == "orientation_reversed" and "not flipped" in note

    def test_allele_mismatch(self):
        assert frequency_identity(_record(ref_allele="C", alt_allele="G"), ANCHOR)[0] == "allele_mismatch"

    def test_matched_allele_is_the_reference(self):
        anchor = AlleleAnchor("GRCh38", "11", 5227002, "T", "T", "x")
        identity, note = frequency_identity(_record(), anchor)
        assert identity == "other_allele" and "reference allele" in note


class TestAdjustmentRequiresVerifiedIdentity:
    def test_unverified_record_never_moves_the_rank(self):
        for identity in ("unverified", "other_allele", "build_mismatch", "position_mismatch",
                         "orientation_reversed", "alleles_swapped", "allele_mismatch"):
            entry = GnomADEntry(rsid="rs1", allele_frequency=0.4, identity=identity)
            assert _calculate_frequency_adjustment(1.0, entry) == 1.0
        assert _calculate_frequency_adjustment(1.0, GnomADEntry("rs1", 0.4, identity="matched")) == 1.0 + COMMON_AF_PENALTY

    def test_invalid_frequency_still_ignored_when_matched(self):
        for af in (float("nan"), -0.1, 1.5, None):
            assert _calculate_frequency_adjustment(1.0, GnomADEntry("rs1", af, identity="matched")) == 1.0


def _db(tmp_path, gnomad_rows, clinvar_identity=True):
    db = AllelioDB(str(tmp_path / "f.db"))
    db.initialize()
    identity = dict(assembly="GRCh38", chromosome="11", position_vcf=5227002) if clinvar_identity else {}
    db.insert_clinvar_batch([
        dict(rsid="rs334", ref_allele="T", alt_allele="A", gene="HBB", clinical_significance="Pathogenic",
             conditions="Hb SS disease", condition_ids="MedGen:C1", review_status="practice guideline",
             last_evaluated="", **identity),
        dict(rsid="rs334", ref_allele="T", alt_allele="G", gene="HBB", clinical_significance="Likely benign",
             conditions="x", condition_ids="MedGen:C2", review_status="criteria provided, single submitter",
             last_evaluated="", **identity),
    ])
    db.insert_gnomad_batch(gnomad_rows)
    return db


def _row(af, **kwargs):
    base = dict(rsid="rs334", chromosome="11", position=5227002, ref_allele="T", alt_allele="A",
                assembly="GRCh38", source_version="v4.1.1", allele_frequency=af, af_popmax=None,
                ac=None, an=None, nhomalt=None, af_afr=None, af_eas=None, af_fin=None, af_nfe=None, af_sas=None)
    base.update(kwargs)
    return base


class TestAnalysis:
    def test_multiallelic_site_keeps_both_alleles_and_selects_the_carried_one(self, tmp_path):
        db = _db(tmp_path, [_row(0.0127), _row(0.0005, alt_allele="G")])
        [a] = analyze_variants([Variant("rs334", "11", 5227002, "TA")], db)
        assert a.gnomad_entry.alt_allele == "A" and a.gnomad_entry.identity == "matched"
        assert a.gnomad_entry.allele_frequency == pytest.approx(0.0127)
        assert sorted((e.alt_allele, e.identity) for e in a.gnomad_entries) == [("A", "matched"), ("G", "other_allele")]
        [g] = analyze_variants([Variant("rs334", "11", 5227002, "TG")], db, include_benign=True)
        assert g.gnomad_entry.alt_allele == "G" and g.gnomad_entry.identity == "matched"

    def test_rank_moves_only_for_a_verified_common_allele(self, tmp_path):
        common = _db(tmp_path / "a", [_row(0.30)])
        [with_penalty] = analyze_variants([Variant("rs334", "11", 5227002, "TA")], common)
        none = _db(tmp_path / "b", [])
        [baseline] = analyze_variants([Variant("rs334", "11", 5227002, "TA")], none)
        assert with_penalty.significance_rank == pytest.approx(baseline.significance_rank + COMMON_AF_PENALTY)
        for label, rows in {
            "build": [_row(0.30, assembly="GRCh37")],
            "position": [_row(0.30, position=5227003)],
            "orientation": [_row(0.30, ref_allele="A", alt_allele="T")],
            "other allele": [_row(0.30, alt_allele="G")],
            "legacy": [_row(0.30, chromosome="", position=None, ref_allele="", alt_allele="", assembly=None)],
        }.items():
            db = _db(tmp_path / label.replace(" ", "_"), rows)
            [r] = analyze_variants([Variant("rs334", "11", 5227002, "TA")], db)
            assert r.significance_rank == baseline.significance_rank, label
            assert r.gnomad_entry is not None and r.gnomad_entry.identity != "matched", label
            assert r.gnomad_entry.allele_frequency == pytest.approx(0.30), label

    def test_build_and_position_mismatch_are_named(self, tmp_path):
        db = _db(tmp_path, [_row(0.30, assembly="GRCh37")])
        [r] = analyze_variants([Variant("rs334", "11", 5227002, "TA")], db)
        assert r.gnomad_entry.identity == "build_mismatch" and "GRCh37" in r.gnomad_entry.identity_note
        db = _db(tmp_path / "p", [_row(0.30, position=5227010)])
        [r] = analyze_variants([Variant("rs334", "11", 5227002, "TA")], db)
        assert r.gnomad_entry.identity == "position_mismatch" and "5227010" in r.gnomad_entry.identity_note

    def test_swapped_alleles_are_reported_not_flipped(self, tmp_path):
        db = _db(tmp_path, [_row(0.30, ref_allele="A", alt_allele="T")])
        [r] = analyze_variants([Variant("rs334", "11", 5227002, "TA")], db)
        assert r.gnomad_entry.identity == "alleles_swapped" and "REF is the matched allele" in r.gnomad_entry.identity_note

    def test_missing_identity_stays_inspectable_context(self, tmp_path):
        legacy = _row(0.30, chromosome="", position=None, ref_allele="", alt_allele="", assembly=None,
                      source_version=None)
        db = _db(tmp_path, [legacy])
        results = analyze_variants([Variant("rs334", "11", 5227002, "TA")], db)
        [r] = results
        assert r.gnomad_entry.identity == "unverified" and "allelio update" in r.gnomad_entry.identity_note
        html = generate_html_report(results, {}, "", {})
        assert "unverified, context only" in html and "Not used for ranking" in html
        summary = format_gnomad_summary(r.gnomad_entry)
        assert summary.startswith("- Allele identity: NOT verified") and "30.0000%" in summary
        assert "Common variant (>5% frequency)" in summary  # heuristic wording preserved
        assert "do not apply a universal BS1 threshold" in summary

    def test_verified_frequency_reads_as_before(self, tmp_path):
        db = _db(tmp_path, [_row(0.30)])
        results = analyze_variants([Variant("rs334", "11", 5227002, "TA")], db)
        [r] = results
        summary = format_gnomad_summary(r.gnomad_entry)
        assert summary.startswith("- Allele identity: verified")
        html = generate_html_report(results, {}, "", {})
        assert "Population Frequency:</span>" in html and "unverified" not in html

    def test_no_source_identity_to_anchor_on(self, tmp_path):
        db = _db(tmp_path, [_row(0.30)], clinvar_identity=False)
        [r] = analyze_variants([Variant("rs334", "11", 5227002, "TA")], db)
        assert r.gnomad_entry.identity == "unverified" and "no checked source identity" in r.gnomad_entry.identity_note

    def test_declared_vcf_evidence_anchors_a_gwas_only_site(self, tmp_path):
        db = AllelioDB(str(tmp_path / "v.db"))
        db.initialize()
        db.insert_gwas_batch([dict(rsid="rs9", trait="Trait", p_value=1e-9, odds_ratio="1.1", mapped_gene="G",
                                   study="s", pubmed_id="1", link="", risk_allele="A")])
        db.insert_gnomad_batch([_row(0.30, rsid="rs9", chromosome="1", position=100)])
        evidence = VCFEvidence("T", ("A",), (0, 1), ("T", "A"), False, reference_declaration="GRCh38")
        [r] = analyze_variants([Variant("rs9", "1", 100, "TA", evidence)], db)
        assert r.gnomad_entry.identity == "matched" and "VCF" in r.gnomad_entry.identity_note
        undeclared = VCFEvidence("T", ("A",), (0, 1), ("T", "A"), False, reference_declaration=None)
        [r] = analyze_variants([Variant("rs9", "1", 100, "TA", undeclared)], db)
        assert r.gnomad_entry.identity == "unverified"

    def test_evidence_export_carries_every_record_and_its_identity(self, tmp_path):
        from allelio.evidence import build_evidence_export
        db = _db(tmp_path, [_row(0.0127), _row(0.0005, alt_allele="G")])
        variants = [Variant("rs334", "11", 5227002, "TA")]
        results = analyze_variants(variants, db)
        finding = build_evidence_export(results, variants, {}, stats=results.stats)["findings"][0]
        assert finding["gnomad_entry"]["identity"] == "matched"
        assert finding["gnomad_entry"]["assembly"] == "GRCh38" and finding["gnomad_entry"]["source_version"] == "v4.1.1"
        assert [e["identity"] for e in finding["gnomad_entries"]] == ["matched", "other_allele"]


class TestMigration:
    def test_rsid_only_table_migrates_with_rows_intact(self, tmp_path):
        db = AllelioDB(str(tmp_path / "old.db"))
        db.cursor.execute("""CREATE TABLE gnomad (rsid TEXT PRIMARY KEY, allele_frequency REAL, af_popmax REAL,
            ac INTEGER, an INTEGER, nhomalt INTEGER, af_afr REAL, af_eas REAL, af_fin REAL, af_nfe REAL, af_sas REAL)""")
        db.cursor.execute("CREATE INDEX idx_gnomad_rsid ON gnomad(rsid)")
        db.cursor.execute("INSERT INTO gnomad VALUES ('rs334', 0.0127, 0.04, 1937, 152294, 9, 0.04, 0, 0, 0.0002, 0.002)")
        db.conn.commit()
        assert not db.gnomad_is_allele_aware()
        db.initialize()
        assert db.gnomad_is_allele_aware()
        [row] = db.lookup_rsid("rs334")["gnomad"]
        assert row["allele_frequency"] == pytest.approx(0.0127) and row["nhomalt"] == 9
        assert (row["ref_allele"], row["alt_allele"], row["assembly"], row["position"]) == ("", "", None, None)
        assert db.get_stats()["gnomad_entries"] == 1
        db.initialize()  # idempotent
        assert db.get_stats()["gnomad_entries"] == 1

    def test_refresh_replaces_rsid_only_rows(self, tmp_path):
        db = AllelioDB(str(tmp_path / "r.db"))
        db.initialize()
        db.insert_gnomad_batch([_row(0.5, chromosome="", position=None, ref_allele="", alt_allele="", assembly=None)])
        db.clear_table("gnomad")
        db.insert_gnomad_batch([_row(0.0127), _row(0.0005, alt_allele="G")])
        rows = db.lookup_rsid("rs334")["gnomad"]
        assert [(r["ref_allele"], r["alt_allele"]) for r in rows] == [("T", "A"), ("T", "G")]


class TestParser:
    def test_format_2_header_and_columns(self, tmp_path):
        path = tmp_path / "g.tsv"
        path.write_text(
            "## Allelio gnomAD frequency file\n## Format: 2\n## Source: gnomAD v4.1.1 genome sites VCFs\n"
            "## Assembly: GRCh38\n"
            "rsid\tchrom\tpos\tref\talt\tAF\tAF_grpmax\tAC\tAN\tnhomalt\tAF_afr\tAF_eas\tAF_fin\tAF_nfe\tAF_sas\n"
            "rs334\tchr11\t5227002\tT\tA\t0.0127\t0.04\t1937\t152294\t9\t0.04\t0\t0\t0.0002\t0.002\n"
            "rs334\t11\t5227002\tT\tG\t0.0005\t.\t.\t.\t.\t.\t.\t.\t.\t.\n"
        )
        assert gnomad_file_header(str(path)) == {"format": "2", "assembly": "GRCh38", "source_version": "v4.1.1"}
        rows = list(parse_gnomad(str(path)))
        assert [(r["chromosome"], r["position"], r["ref_allele"], r["alt_allele"]) for r in rows] == [
            ("11", 5227002, "T", "A"), ("11", 5227002, "T", "G"),
        ]
        assert rows[0]["assembly"] == "GRCh38" and rows[0]["source_version"] == "v4.1.1"
        assert rows[1]["allele_frequency"] == pytest.approx(0.0005) and rows[1]["ac"] is None

    def test_format_1_file_reads_without_identity(self):
        path = Path(__file__).parent / "fixtures" / "example_gnomad.tsv.gz"
        legacy = Path(__file__).parent / "fixtures" / "legacy_gnomad_format1.tsv.gz"
        with gzip.open(legacy, "wt", encoding="utf-8") as out:
            out.write("## Allelio gnomAD frequency file\n## Source: gnomAD v4.1.1 genome sites VCFs\n"
                      "rsid\tAF\tAF_grpmax\tAC\tAN\tnhomalt\tAF_afr\tAF_eas\tAF_fin\tAF_nfe\tAF_sas\n"
                      "rs334\t0.0127\t0.04\t1937\t152294\t9\t0.04\t0\t0\t0.0002\t0.002\n")
        try:
            assert gnomad_file_header(str(legacy)) == {"format": "1", "assembly": None, "source_version": "v4.1.1"}
            [row] = parse_gnomad(str(legacy))
            assert (row["ref_allele"], row["alt_allele"], row["assembly"], row["position"]) == ("", "", None, None)
            assert row["allele_frequency"] == pytest.approx(0.0127)
        finally:
            legacy.unlink()
        # The shipped example fixture is format 2 with an assembly
        assert gnomad_file_header(str(path))["assembly"] == "GRCh38"


class TestBuildScript:
    def test_per_allele_values_are_not_the_first_alleles(self):
        info = parse_info_field("AF=0.1,0.002;AC=10,2;AN=100;nhomalt=1,0;AF_afr=0.2,0.001")
        assert allele_values(info, 0)[:5] == ["0.1", ".", "10", "100", "1"]
        assert allele_values(info, 1)[:5] == ["0.002", ".", "2", "100", "0"]
        assert allele_values(info, 2)[0] == "."  # fewer values than alleles: never another allele's number

    def test_emit_records_writes_one_row_per_alternate_allele(self):
        class Out:
            def __init__(self):
                self.lines = []

            def write(self, text):
                self.lines.append(text)

        out = Out()
        vcf = [
            "##fileformat=VCFv4.2\n",
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n",
            "chr11\t5227002\trs334\tT\tA,G\t.\tPASS\tAF=0.0127,0.0005;AC=1937,76;AN=152294;nhomalt=9,0\n",
            "chr1\t100\trs1;rs2\tC\tT,*\t.\tPASS\tAF=0.5,0.1;AN=10\n",
            "chr1\t200\t.\tC\tT\t.\tPASS\tAF=0.5\n",
        ]
        count = emit_records(vcf, out, 0, array_sites={"rs334", "rs1"})
        rows = [line.rstrip("\n").split("\t") for line in out.lines]
        assert count == 3
        assert rows[0][:6] == ["rs334", "11", "5227002", "T", "A", "0.0127"] and rows[0][7] == "1937"
        assert rows[1][:6] == ["rs334", "11", "5227002", "T", "G", "0.0005"] and rows[1][7] == "76"
        assert rows[2][:6] == ["rs1", "1", "100", "C", "T", "0.5"]  # rs2 not in the array set; '*' skipped
