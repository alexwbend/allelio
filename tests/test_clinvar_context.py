"""ClinVar condition and classification context survives import and reporting.

Fixtures in tests/fixtures/clinvar_context/ are synthetic rows written in the
two variant_summary.txt layouts Allelio reads: the current one with the
2024 germline/somatic split, and the earlier one without it. Genes, rsIDs,
identifiers and accessions are invented.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from allelio.ai.prompts import build_variant_prompt
from allelio.analysis.lookup import ClinVarEntry, analyze_variants
from allelio.database.clinvar import (
    CLASSIFICATION_GERMLINE, CLASSIFICATION_UNSPLIT, CLINVAR_COLUMNS, _column_map, parse_clinvar,
)
from allelio.database.store import AllelioDB
from allelio.evidence import build_evidence_export
from allelio.parsers.base import Variant
from allelio.report import generate_html_report

FIXTURES = Path(__file__).parent / "fixtures" / "clinvar_context"
SPLIT = FIXTURES / "variant_summary_split.tsv"
UNSPLIT = FIXTURES / "variant_summary_unsplit.tsv"


class TestParser:
    def test_header_pins_the_documented_layout(self):
        header = SPLIT.read_text().splitlines()[0]
        columns = _column_map(header)
        assert columns == {**CLINVAR_COLUMNS}  # every documented index agrees with the header
        old = _column_map(UNSPLIT.read_text().splitlines()[0])
        assert old["SomaticClinicalImpact"] is None and old["Oncogenicity"] is None
        assert old["AlternateAlleleVCF"] == 33

    def test_reordered_columns_are_found_by_name(self, tmp_path):
        lines = SPLIT.read_text().splitlines()
        header, body = lines[0].split("\t"), [l.split("\t") for l in lines[1:2]]
        # #AlleleID stays first (every real file starts with it); the rest moves.
        order = [0] + list(range(34, len(header))) + list(range(1, 34))[::-1]
        path = tmp_path / "reordered.tsv"
        path.write_text("\t".join(header[i] for i in order) + "\n"
                        + "\n".join("\t".join(r[i] for i in order) for r in body) + "\n")
        [row] = parse_clinvar(str(path))
        assert row["rsid"] == "rs8000001" and row["alt_allele"] == "G" and row["number_submitters"] == 5

    def test_multiple_conditions_and_rcvs_are_kept_verbatim(self):
        row = next(r for r in parse_clinvar(str(SPLIT)) if r["rsid"] == "rs8000001")
        assert row["conditions"] == "Condition one|Condition two|not provided"
        assert row["condition_ids"].split("|")[1] == "MONDO:MONDO:0900012,MedGen:C12"
        assert row["rcv_accessions"] == "RCV000000011|RCV000000012|RCV000000013"
        assert row["number_submitters"] == 5 and row["classification_type"] == CLASSIFICATION_GERMLINE
        assert row["origin"] == "germline" and row["variant_type"] == "single nucleotide variant"

    def test_mixed_context_keeps_somatic_assertions_apart(self):
        row = next(r for r in parse_clinvar(str(SPLIT)) if r["rsid"] == "rs8000002")
        assert row["clinical_significance"] == "Pathogenic"
        assert (row["origin"], row["origin_simple"]) == ("germline;somatic", "germline/somatic")
        assert row["somatic_clinical_impact"] == "Tier I - Strong"
        assert row["somatic_review_status"] == "criteria provided, single submitter"
        assert row["somatic_last_evaluated"] == "Mar 01, 2025"
        assert row["oncogenicity"] == "Oncogenic" and row["oncogenicity_last_evaluated"] == "Mar 01, 2025"

    def test_missing_fields_are_none_not_defaults(self):
        row = next(r for r in parse_clinvar(str(SPLIT)) if r["rsid"] == "rs8000003")
        assert row["origin"] is None and row["origin_simple"] == "not provided"
        assert row["rcv_accessions"] is None and row["last_evaluated"] is None
        assert row["number_submitters"] == 0 and row["somatic_clinical_impact"] is None

    def test_pre_split_file_reads_as_unsplit(self):
        [row] = parse_clinvar(str(UNSPLIT))
        assert row["classification_type"] == CLASSIFICATION_UNSPLIT
        assert row["origin_simple"] == "germline/somatic"
        assert row["somatic_clinical_impact"] is None and row["oncogenicity"] is None

    def test_distinct_records_for_one_allele_are_both_emitted(self):
        rows = [r for r in parse_clinvar(str(SPLIT)) if r["rsid"] == "rs8000004"]
        assert [(r["allele_id"], r["clinical_significance"]) for r in rows] == [
            ("41", "Benign"), ("42", "Conflicting classifications of pathogenicity"),
        ]
        par = [r for r in parse_clinvar(str(SPLIT)) if r["rsid"] == "rs8000005"]
        assert [(r["allele_id"], r["chromosome"]) for r in par] == [("51", "X"), ("51", "Y")]


@pytest.fixture
def db(tmp_path):
    db = AllelioDB(str(tmp_path / "ctx.db"))
    db.initialize()
    db.insert_clinvar_batch(list(parse_clinvar(str(SPLIT))))
    return db


class TestStore:
    def test_conflicting_records_are_not_merged(self, db):
        rows = db.lookup_rsid("rs8000004")["clinvar"]
        assert [(r["allele_id"], r["clinical_significance"]) for r in rows] == [
            ("41", "Benign"), ("42", "Conflicting classifications of pathogenicity"),
        ]
        par = db.lookup_rsid("rs8000005")["clinvar"]
        assert [r["chromosome"] for r in par] == ["X", "Y"]
        assert db.get_stats()["clinvar_entries"] == 8

    def test_context_columns_round_trip(self, db):
        [row] = db.lookup_rsid("rs8000002")["clinvar"]
        assert row["somatic_clinical_impact"] == "Tier I - Strong" and row["origin_simple"] == "germline/somatic"
        assert row["rcv_accessions"] == "RCV000000021|RCV000000022" and row["classification_type"] == "germline"

    def test_legacy_allele_keyed_database_migrates_without_inventing_context(self, tmp_path):
        path = tmp_path / "legacy.db"
        with sqlite3.connect(path) as con:
            con.execute("CREATE TABLE clinvar (rsid TEXT NOT NULL, ref_allele TEXT NOT NULL DEFAULT '', "
                        "alt_allele TEXT NOT NULL DEFAULT '', gene TEXT, clinical_significance TEXT, conditions TEXT, "
                        "review_status TEXT, last_evaluated TEXT, assembly TEXT, chromosome TEXT, position_vcf INTEGER, "
                        "allele_id TEXT, variation_id TEXT, hgnc_id TEXT, PRIMARY KEY (rsid, ref_allele, alt_allele))")
            con.execute("INSERT INTO clinvar VALUES ('rs1','A','G','GENE','Pathogenic','Cond','practice guideline','',"
                        "'GRCh38','1',100,'77','1077','HGNC:1')")
            con.execute("INSERT INTO clinvar VALUES ('rs2','C','T','GENE','Benign','','','',NULL,NULL,NULL,NULL,NULL,NULL)")
        db = AllelioDB(str(path))
        db.initialize()
        db.initialize()
        assert db._primary_key("clinvar") == list(db.CLINVAR_KEY)
        [row] = db.lookup_rsid("rs1")["clinvar"]
        assert (row["chromosome"], row["allele_id"], row["position_vcf"]) == ("1", "77", 100)
        assert row["classification_type"] is None and row["origin"] is None and row["somatic_clinical_impact"] is None
        [row2] = db.lookup_rsid("rs2")["clinvar"]
        assert (row2["chromosome"], row2["allele_id"]) == ("", "")
        [r] = analyze_variants([Variant("rs1", "1", 100, "AG")], db)
        assert r.clinvar_entries[0].classification_type == "unknown"
        assert r.clinvar_entries[0].context_phrases()[0].startswith("classification type unknown")

    def test_refresh_after_migration_replaces_rows(self, tmp_path):
        db = AllelioDB(str(tmp_path / "r.db"))
        db.initialize()
        db.insert_clinvar_batch([dict(rsid="rs8000004", ref_allele="T", alt_allele="C", gene="SYNCTX",
                                      clinical_significance="Benign", conditions="", review_status="", last_evaluated="")])
        db.clear_table("clinvar")
        db.insert_clinvar_batch(list(parse_clinvar(str(SPLIT))))
        assert len(db.lookup_rsid("rs8000004")["clinvar"]) == 2


def _one(db, rsid, chrom, pos, genotype, **kwargs):
    [r] = analyze_variants([Variant(rsid, chrom, pos, genotype)], db, **kwargs)
    return r


class TestAnalysis:
    def test_source_classification_match_and_rank_are_separate_fields(self, db):
        r = _one(db, "rs8000001", "1", 2001, "AG")
        [entry] = r.clinvar_entries
        assert entry.clinical_significance == "Pathogenic"
        assert entry.allele_match == "carried" and entry.allele_match_note == "1 copy of G"
        assert entry.display_rank == pytest.approx(1.0 - 0.2)
        assert r.significance_rank == pytest.approx(entry.display_rank)
        assert entry.rcv_list == ["RCV000000011", "RCV000000012", "RCV000000013"]

    def test_conflicting_records_stay_distinct_and_ranked(self, db):
        r = _one(db, "rs8000004", "1", 2004, "TC", include_benign=True)
        assert [(e.allele_id, e.clinical_significance, e.allele_match) for e in r.clinvar_entries] == [
            ("42", "Conflicting classifications of pathogenicity", "carried"), ("41", "Benign", "carried"),
        ]
        assert r.clinvar_entries[0].display_rank < r.clinvar_entries[1].display_rank
        assert r.category == "Unknown"  # the conflicting record is primary; the benign one is not hidden

    def test_pseudoautosomal_pair_is_kept(self, db):
        r = _one(db, "rs8000005", "X", 2005, "CG")
        assert sorted(e.chromosome for e in r.clinvar_entries) == ["X", "Y"]
        assert r.category == "Health Conditions"

    def test_mixed_context_phrases(self, db):
        r = _one(db, "rs8000002", "1", 2002, "CT")
        phrases = r.clinvar_entries[0].context_phrases()
        assert phrases[0] == "germline classification (aggregate across the listed conditions)"
        assert "origin: germline/somatic (germline;somatic)" in phrases
        assert "somatic clinical impact: Tier I - Strong; criteria provided, single submitter; Mar 01, 2025" in phrases
        assert "oncogenicity: Oncogenic; criteria provided, single submitter; Mar 01, 2025" in phrases
        assert any(p.startswith("aggregates 2 condition records (RCV), 3 submitters") for p in phrases)

    def test_missing_context_reads_unknown_not_germline(self, db):
        r = _one(db, "rs8000003", "1", 2003, "GA", include_benign=True)
        phrases = r.clinvar_entries[0].context_phrases()
        assert "origin: not provided" in phrases and not any("somatic" in p for p in phrases)

    def test_somatic_only_record_is_not_a_germline_finding(self, db):
        r = _one(db, "rs8000006", "1", 2006, "AC", include_benign=True)
        assert r.category != "Health Conditions"
        phrases = r.clinvar_entries[0].context_phrases()
        assert "origin: somatic" in phrases and any(p.startswith("somatic clinical impact: Tier II") for p in phrases)

    def test_unsplit_file_is_labelled(self, tmp_path):
        db = AllelioDB(str(tmp_path / "old.db"))
        db.initialize()
        db.insert_clinvar_batch(list(parse_clinvar(str(UNSPLIT))))
        r = _one(db, "rs8000007", "1", 2007, "GT")
        assert r.clinvar_entries[0].classification_type == "unsplit"
        assert r.clinvar_entries[0].context_phrases()[0].startswith("classification from a pre-2024 ClinVar file")


class TestSurfaces:
    def test_report_prompt_and_export_agree(self, db):
        variants = [Variant("rs8000002", "1", 2002, "CT"), Variant("rs8000004", "1", 2004, "TC")]
        results = analyze_variants(variants, db, include_benign=True)
        html = generate_html_report(results, {}, "", {})
        assert "Classification context:" in html
        assert "somatic clinical impact: Tier I - Strong" in html
        assert "Other ClinVar records for this site: Benign (carried, record 41)" in html
        prompt = build_variant_prompt(next(r for r in results if r.rsid == "rs8000002"))
        assert "allele match: carried (1 copy of T)" in prompt
        assert "oncogenicity: Oncogenic" in prompt and "germline classification (aggregate" in prompt
        assert "never present it as a germline finding" in prompt
        document = build_evidence_export(results, variants, {}, stats=results.stats)
        json.dumps(document)
        by = {f["rsid"]: f for f in document["findings"]}
        entry = by["rs8000002"]["clinvar_entries"][0]
        assert entry["classification_type"] == "germline" and entry["somatic_clinical_impact"] == "Tier I - Strong"
        assert entry["allele_match"] == "carried" and entry["display_rank"] == pytest.approx(0.9)
        assert [e["allele_id"] for e in by["rs8000004"]["clinvar_entries"]] == ["42", "41"]

    def test_web_payload_context(self, db):
        from allelio.web.app import app  # noqa: F401  (routes import through the app)
        from allelio.web.routes import _classification_context_of
        r = _one(db, "rs8000004", "1", 2004, "TC", include_benign=True)
        context = _classification_context_of(r)
        assert context["phrases"][0].startswith("germline classification")
        assert [(x["allele_id"], x["allele_match"]) for x in context["records"]] == [("42", "carried"), ("41", "carried")]
        assert context["records"][1]["display_rank"] > context["records"][0]["display_rank"]
        from allelio.analysis.lookup import VariantResult
        assert _classification_context_of(VariantResult("rs0")) is None  # GWAS-only results give None

    def test_fallback_text_names_context(self, db):
        from allelio.ai.engine import AIEngine
        r = _one(db, "rs8000002", "1", 2002, "CT")
        text = AIEngine.__new__(AIEngine)._fallback_explanation(r, "offline")
        assert "somatic clinical impact: Tier I - Strong" in text and "origin: germline/somatic" in text
