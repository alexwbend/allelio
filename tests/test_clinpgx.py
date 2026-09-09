"""ClinPGx clinical annotations: parsing, genotype matching, and reporting."""

from pathlib import Path

import pytest

from allelio.analysis.lookup import (
    PGX_LEVEL_RANKS,
    _match_pgx,
    analyze_variants,
)
from allelio.database.clinpgx import (
    clinpgx_release_date,
    extract_bundle,
    level_rank,
    parse_clinpgx,
)
from allelio.database.store import AllelioDB
from allelio.parsers.base import Variant

FIXTURE = Path(__file__).parent / "fixtures" / "example_clinpgx"


class TestParser:
    def test_single_rsid_annotations_only(self):
        rows = list(parse_clinpgx(str(FIXTURE)))
        assert {r["rsid"] for r in rows} == {"rs9923231", "rs4149056", "rs1042713"}
        assert not any("*" in (r["genotype"] or "") for r in rows)

    def test_one_row_per_genotype_with_its_text(self):
        rows = [r for r in parse_clinpgx(str(FIXTURE)) if r["annotation_id"] == "900000001"]
        assert sorted(r["genotype"] for r in rows) == ["CC", "CT", "TT"]
        ct = next(r for r in rows if r["genotype"] == "CT")
        assert ct["level"] == "1A" and ct["drugs"] == "warfarin" and "CT genotype" in ct["annotation_text"]
        assert ct["url"].startswith("https://")

    def test_release_date_from_created_marker(self):
        assert clinpgx_release_date(str(FIXTURE)) == "2026-01-01"

    def test_extract_bundle_and_zip_release_date(self, tmp_path):
        import zipfile
        z = tmp_path / "b.zip"
        with zipfile.ZipFile(z, "w") as zf:
            for f in FIXTURE.iterdir():
                if f.name != "README.md":
                    zf.write(f, f"clinicalAnnotations/{f.name}")
        assert clinpgx_release_date(str(z)) == "2026-01-01"
        out = extract_bundle(str(z), str(tmp_path / "out"))
        assert (out / "clinical_annotations.tsv").exists() and (out / "CREATED_2026-01-01.txt").exists()
        assert len(list(parse_clinpgx(str(out)))) == len(list(parse_clinpgx(str(FIXTURE))))

    def test_level_rank_order(self):
        assert [level_rank(l) for l in ("1A", "1B", "2A", "2B", "3", "4", "zz")] == [0, 1, 2, 3, 4, 5, 6]


def _rows():
    return [r for r in parse_clinpgx(str(FIXTURE)) if r["rsid"] == "rs9923231"]


class TestMatching:
    def test_matches_the_persons_genotype(self):
        [e] = _match_pgx("CT", _rows())
        assert e.genotype == "CT" and "CT genotype" in e.annotation_text and e.strand_flipped is False

    def test_genotype_order_does_not_matter(self):
        [e] = _match_pgx("TC", _rows())
        assert e.genotype == "CT"

    def test_complement_strand_is_used_and_flagged(self):
        [e] = _match_pgx("GA", _rows())  # complement of CT
        assert e.genotype == "CT" and e.strand_flipped is True

    def test_complement_not_used_at_ambiguous_site(self):
        rows = [dict(r, genotype=g) for r, g in zip(_rows(), ("AA", "AT", "TT"))]
        assert _match_pgx("CG", rows) == []

    def test_no_match_when_letters_unrelated(self):
        assert _match_pgx("AC", _rows()) == []

    def test_no_call_and_haploid_are_unmatched(self):
        assert _match_pgx("--", _rows()) == [] and _match_pgx("C", _rows()) == []

    def test_level_filter_default_hides_level_3(self):
        rows = [r for r in parse_clinpgx(str(FIXTURE)) if r["rsid"] == "rs4149056"]
        default = _match_pgx("CT", rows)
        assert [e.level for e in default] == ["1A"]
        with_3 = _match_pgx("CT", rows, min_level="3")
        assert [e.level for e in with_3] == ["1A", "3"]


@pytest.fixture
def db(tmp_path):
    db = AllelioDB(str(tmp_path / "p.db"))
    db.initialize()
    db.insert_clinpgx_batch(list(parse_clinpgx(str(FIXTURE))))
    db.insert_clinvar_batch([
        {"rsid": "rs1042713", "ref_allele": "G", "alt_allele": "A", "gene": "ADRB2",
         "clinical_significance": "drug response", "conditions": "salmeterol response",
         "review_status": "reviewed by expert panel", "last_evaluated": ""},
    ])
    db.insert_gnomad_batch([{"rsid": "rs9923231", "allele_frequency": 0.4, "af_popmax": 0.5, "ac": 1, "an": 2,
                             "nhomalt": 0, "af_afr": None, "af_eas": None, "af_fin": None, "af_nfe": None, "af_sas": None}])
    return db


class TestAnalysis:
    def test_pgx_only_site_is_reported_and_ranked_by_level(self, db):
        [r] = analyze_variants([Variant("rs9923231", "16", 31107689, "CT")], db)
        assert r.category == "Pharmacogenomics" and r.pgx_level == "1A"
        assert r.pgx_entries[0].drugs == "warfarin"
        # Common allele, but no frequency downgrade for a drug-response finding.
        assert r.significance_rank == PGX_LEVEL_RANKS["1A"]

    def test_unmatched_genotype_is_not_a_finding(self, db):
        rows = analyze_variants([Variant("rs9923231", "16", 31107689, "AC")], db)
        assert rows == []

    def test_clinvar_drug_response_and_pgx_share_the_card(self, db):
        [r] = analyze_variants([Variant("rs1042713", "5", 148206440, "AG")], db)
        assert r.category == "Pharmacogenomics" and r.pgx_level == "2A"
        assert r.clinvar_entries and r.alt_copies == 1

    def test_stats_count_pgx_only_sites_as_annotated(self, db):
        from allelio.analysis.lookup import analyze_variants_with_stats
        _, stats = analyze_variants_with_stats([Variant("rs9923231", "16", 31107689, "CT")], db)
        assert stats.annotated_sites == 1
