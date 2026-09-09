"""ClinGen gene-disease validity: parsing, inheritance, and the carrier rule."""

from pathlib import Path

import pytest

from allelio.analysis.lookup import (
    CARRIER_RANK_SHIFT,
    ClinGenEntry,
    VariantCategory,
    _carrier,
    _determine_category,
    _inheritance,
    analyze_variants,
)
from allelio.analysis.zygosity import ZygosityCall, Zygosity
from allelio.database.clingen import clingen_release_date, parse_clingen
from allelio.database.store import AllelioDB
from allelio.parsers.base import Variant

FIXTURE = Path(__file__).parent / "fixtures" / "example_clingen.csv"


class TestParser:
    def test_skips_preamble_and_reads_rows(self):
        rows = list(parse_clingen(str(FIXTURE)))
        assert rows and all(r["gene"] for r in rows)
        hfe = [r for r in rows if r["gene"] == "HFE"]
        assert hfe and hfe[0]["moi"] == "AR" and hfe[0]["classification"] == "Definitive"
        assert hfe[0]["disease"].startswith("hemochromatosis")
        assert hfe[0]["report_url"].startswith("https://")

    def test_release_date_from_preamble(self):
        assert clingen_release_date(str(FIXTURE)) == "2026-09-09"

    def test_release_date_missing(self, tmp_path):
        f = tmp_path / "x.csv"
        f.write_text('"GENE SYMBOL","MOI"\n"A","AR"\n')
        assert clingen_release_date(str(f)) is None
        assert list(parse_clingen(str(f)))[0]["moi"] == "AR"


def _e(gene, moi, cls="Definitive", disease="d"):
    return ClinGenEntry(gene=gene, disease=disease, moi=moi, classification=cls)


class TestInheritance:
    def test_not_curated(self):
        assert _inheritance([]) == ("not curated", None)

    def test_recessive_only(self):
        inh, note = _inheritance([_e("HFE", "AR", disease="hemochromatosis type 1")])
        assert inh == "autosomal recessive" and "hemochromatosis" in note and "autosomal recessive" in note

    def test_dominant_only(self):
        assert _inheritance([_e("BRCA1", "AD")])[0] == "autosomal dominant"

    def test_mixed(self):
        assert _inheritance([_e("HBB", "AR"), _e("HBB", "AD")])[0].startswith("mixed")

    def test_limited_curations_do_not_decide(self):
        inh, note = _inheritance([_e("G", "AD", cls="Limited"), _e("G", "AR", cls="Definitive")])
        assert inh == "autosomal recessive"
        inh, note = _inheritance([_e("G", "AD", cls="Disputed")])
        assert inh == "not established" and "Disputed" in note

    def test_x_linked(self):
        assert _inheritance([_e("G6PD", "XL")])[0] == "X-linked"


class TestCarrierRule:
    def het(self):
        return ZygosityCall(Zygosity.HETEROZYGOUS, 1, "A")

    def test_one_copy_recessive_is_carrier(self):
        assert _carrier("autosomal recessive", self.het(), "GA") is True

    def test_two_copies_recessive_is_not(self):
        assert _carrier("autosomal recessive", ZygosityCall(Zygosity.HOMOZYGOUS_ALTERNATE, 2, "A"), "AA") is False

    def test_one_copy_dominant_is_not(self):
        assert _carrier("autosomal dominant", self.het(), "GA") is False

    def test_mixed_is_not(self):
        assert _carrier("mixed (dominant and recessive conditions)", self.het(), "GA") is False

    def test_x_linked_diploid_het_is_carrier_hemizygous_is_not(self):
        assert _carrier("X-linked", self.het(), "GA") is True
        assert _carrier("X-linked", ZygosityCall(Zygosity.HEMIZYGOUS_ALTERNATE, 1, "A"), "A") is False


class TestBenignCategory:
    def test_benign_is_its_own_category(self):
        from allelio.analysis.lookup import ClinVarEntry
        assert _determine_category(ClinVarEntry("rs1", clinical_significance="Benign"), []) == "Benign"
        assert _determine_category(ClinVarEntry("rs1", clinical_significance="Likely benign"), []) == "Benign"
        assert VariantCategory.BENIGN.value == "Benign"


@pytest.fixture
def db(tmp_path):
    db = AllelioDB(str(tmp_path / "c.db"))
    db.initialize()
    db.insert_clinvar_batch([
        {"rsid": "rs1800562", "ref_allele": "G", "alt_allele": "A", "gene": "HFE",
         "clinical_significance": "Pathogenic", "conditions": "Hemochromatosis type 1",
         "review_status": "practice guideline", "last_evaluated": ""},
        {"rsid": "rs28897696", "ref_allele": "G", "alt_allele": "T", "gene": "BRCA1",
         "clinical_significance": "Pathogenic", "conditions": "Breast-ovarian cancer",
         "review_status": "reviewed by expert panel", "last_evaluated": ""},
        {"rsid": "rs9", "ref_allele": "C", "alt_allele": "T", "gene": "NOCURATION",
         "clinical_significance": "Pathogenic", "conditions": "x",
         "review_status": "criteria provided, single submitter", "last_evaluated": ""},
    ])
    db.insert_clingen_batch([
        {"gene": "HFE", "hgnc_id": "HGNC:4886", "disease": "hemochromatosis type 1", "mondo_id": "MONDO:0021001",
         "moi": "AR", "classification": "Definitive", "report_url": "https://x", "classification_date": "2020-01-01"},
        {"gene": "BRCA1", "hgnc_id": "HGNC:1100", "disease": "BRCA1-related cancer predisposition", "mondo_id": "M",
         "moi": "AD", "classification": "Definitive", "report_url": "https://x", "classification_date": "2020-01-01"},
        {"gene": "BRCA1", "hgnc_id": "HGNC:1100", "disease": "Fanconi anemia, complementation group S", "mondo_id": "M2",
         "moi": "AR", "classification": "Definitive", "report_url": "https://x", "classification_date": "2020-01-01"},
    ])
    return db


class TestAnalysisAppliesInheritance:
    def test_het_in_recessive_only_gene_is_carrier_status_a_tier_down(self, db):
        [het] = analyze_variants([Variant("rs1800562", "6", 26093141, "GA")], db)
        [hom] = analyze_variants([Variant("rs1800562", "6", 26093141, "AA")], db)
        assert het.category == "Carrier Status" and het.inheritance == "autosomal recessive"
        assert hom.category == "Health Conditions"
        assert het.significance_rank == pytest.approx(hom.significance_rank + CARRIER_RANK_SHIFT)
        assert "hemochromatosis" in het.inheritance_note
        assert [e.moi for e in het.clingen_entries] == ["AR"]

    def test_het_in_mixed_gene_stays_health_condition(self, db):
        [r] = analyze_variants([Variant("rs28897696", "17", 41215920, "GT")], db)
        assert r.category == "Health Conditions" and r.inheritance.startswith("mixed")

    def test_gene_without_curation(self, db):
        [r] = analyze_variants([Variant("rs9", "1", 1, "CT")], db)
        assert r.category == "Health Conditions" and r.inheritance == "not curated" and r.clingen_entries == []
