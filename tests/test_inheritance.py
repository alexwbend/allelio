"""Condition-specific inheritance: ClinVar conditions matched to ClinGen by MONDO id.

The challenge fixtures in tests/fixtures/challenge_inheritance/ are synthetic:
invented genes, diseases, identifiers, and rsIDs, written in the real ClinVar
and ClinGen file formats so the real parsers load them.
"""

import json
from pathlib import Path

import pytest

from allelio.analysis import inheritance as inh
from allelio.analysis.inheritance import (
    CONDITION_ALIASES,
    ClinGenEntry,
    parse_conditions,
    resolve_inheritance,
)
from allelio.analysis.lookup import CARRIER_RANK_SHIFT, analyze_variants
from allelio.database.clingen import parse_clingen
from allelio.database.clinvar import parse_clinvar
from allelio.database.store import AllelioDB
from allelio.evidence import build_evidence_export
from allelio.parsers.base import Variant

FIXTURES = Path(__file__).parent / "fixtures" / "challenge_inheritance"


class TestParseConditions:
    def test_pairs_names_with_identifiers_entry_by_entry(self):
        refs = parse_conditions(
            "Hemochromatosis type 1|not provided",
            "MONDO:MONDO:0021001,MedGen:C3469186,OMIM:235200|MedGen:C3661900",
        )
        assert [(r.name, r.mondo_id) for r in refs] == [
            ("Hemochromatosis type 1", "MONDO:0021001"), ("not provided", None),
        ]
        assert refs[0].identifiers == ["MONDO:MONDO:0021001", "MedGen:C3469186", "OMIM:235200"]

    def test_co_occurring_conditions_in_one_entry(self):
        refs = parse_conditions(
            "Akinesia;Rigidity|Gaucher disease",
            "Human Phenotype Ontology:HP:0002304,MedGen:C0085623;Human Phenotype Ontology:HP:0002063|MONDO:MONDO:0018150",
        )
        assert [r.name for r in refs] == ["Akinesia", "Rigidity", "Gaucher disease"]
        assert [r.mondo_id for r in refs] == [None, None, "MONDO:0018150"]

    def test_misaligned_columns_keep_identifiers_without_names(self):
        refs = parse_conditions("A|B|C", "MONDO:MONDO:0000001|MedGen:C2")
        assert [(r.name, r.mondo_id) for r in refs] == [(None, "MONDO:0000001"), (None, None)]

    def test_names_only_when_identifiers_absent(self):
        assert [r.name for r in parse_conditions("A|B", None)] == ["A", "B"]
        assert [r.name for r in parse_conditions("A", "")] == ["A"]
        assert parse_conditions(None, None) == []

    def test_plain_mondo_prefix_and_non_numeric_ids(self):
        refs = parse_conditions("x", "MONDO:0000001,MONDO:MONDO:abc")
        assert refs[0].mondo_id == "MONDO:0000001"


def _cg(gene, mondo, moi, cls="Definitive", disease=None):
    return ClinGenEntry(gene=gene, disease=disease or f"{gene} {moi}", moi=moi,
                        classification=cls, mondo_id=mondo)


class TestResolveInheritance:
    def test_not_curated_gene(self):
        r = resolve_inheritance("x", "MONDO:MONDO:1", [])
        assert (r.status, r.inheritance, r.note) == ("not_curated", "not curated", None)

    def test_resolved_recessive_records_mapping_and_condition(self):
        r = resolve_inheritance("HFE cond|not provided", "MONDO:MONDO:0021001|MedGen:C1",
                                [_cg("HFE", "MONDO:0021001", "AR", disease="hemochromatosis type 1")])
        assert r.status == "resolved" and r.inheritance == "autosomal recessive"
        assert r.condition == "hemochromatosis type 1" and r.condition_id == "MONDO:0021001"
        assert r.mapping == {"method": "mondo-exact", "version": "1.1"}
        assert "mondo-exact 1.1" in r.note
        assert r.gene_inheritance == "autosomal recessive"

    def test_resolved_against_one_condition_of_a_mixed_gene(self):
        curations = [_cg("G", "MONDO:1", "AD"), _cg("G", "MONDO:2", "AR")]
        r = resolve_inheritance("a", "MONDO:MONDO:2", curations)
        assert r.status == "resolved" and r.inheritance == "autosomal recessive"
        assert r.gene_inheritance.startswith("mixed") and "gene-level: mixed" in r.note
        assert [e.mondo_id for e in r.matched] == ["MONDO:2"]

    def test_conflicting_when_matched_conditions_differ(self):
        curations = [_cg("G", "MONDO:1", "AD"), _cg("G", "MONDO:2", "AR")]
        r = resolve_inheritance("a|b", "MONDO:MONDO:1|MONDO:MONDO:2", curations)
        assert r.status == "conflicting"
        assert r.inheritance == "conflicting (matched conditions differ: autosomal dominant, autosomal recessive)"
        assert len(r.matched) == 2 and "not decided here" in r.note

    def test_unmapped_keeps_identifiers_and_gene_context(self):
        r = resolve_inheritance("a", "MONDO:MONDO:9", [_cg("G", "MONDO:1", "AR")])
        assert r.status == "unmapped" and r.inheritance.startswith("unresolved")
        assert r.unmatched_condition_ids == ["MONDO:9"] and r.matched == []
        assert "gene-level: autosomal recessive" in r.note

    def test_no_identifiers(self):
        r = resolve_inheritance("not provided", "MedGen:C3661900", [_cg("G", "MONDO:1", "AR")])
        assert r.status == "no_identifiers" and "not provided" in r.note
        r = resolve_inheritance("x", "", [_cg("G", "MONDO:1", "AR")])
        assert r.status == "no_identifiers"

    def test_identifiers_not_stored_points_at_refresh(self):
        r = resolve_inheritance("x", None, [_cg("G", "MONDO:1", "AR")])
        assert r.status == "identifiers_not_stored" and "allelio update" in r.note

    def test_disputed_match_is_not_established(self):
        r = resolve_inheritance("a", "MONDO:MONDO:1", [_cg("G", "MONDO:1", "AD", cls="Disputed")])
        assert r.status == "not_established" and r.inheritance == "not established (Disputed)"

    def test_limited_match_does_not_decide_but_established_one_does(self):
        curations = [_cg("G", "MONDO:1", "AD", cls="Limited"), _cg("G", "MONDO:2", "AR")]
        r = resolve_inheritance("a|b", "MONDO:MONDO:1|MONDO:MONDO:2", curations)
        assert r.status == "resolved" and r.inheritance == "autosomal recessive"

    def test_two_recessive_conditions_agree(self):
        curations = [_cg("G", "MONDO:1", "AR"), _cg("G", "MONDO:2", "AR", cls="Strong")]
        r = resolve_inheritance("a|b", "MONDO:MONDO:1|MONDO:MONDO:2", curations)
        assert r.status == "resolved" and len(r.matched) == 2

    def test_undetermined_mode(self):
        r = resolve_inheritance("a", "MONDO:MONDO:1", [_cg("G", "MONDO:1", None)])
        assert r.status == "conflicting" and r.inheritance == "undetermined"

    def test_explicit_alias_table_is_honoured_and_names_are_not(self, monkeypatch):
        curations = [_cg("G", "MONDO:2", "AR", disease="the condition")]
        assert resolve_inheritance("the condition", "MONDO:MONDO:1", curations).status == "unmapped"
        monkeypatch.setitem(CONDITION_ALIASES, "MONDO:1", "MONDO:2")
        assert resolve_inheritance("the condition", "MONDO:MONDO:1", curations).status == "resolved"


@pytest.fixture
def challenge_db(tmp_path):
    db = AllelioDB(str(tmp_path / "challenge.db"))
    db.initialize()
    db.insert_clinvar_batch(list(parse_clinvar(str(FIXTURES / "clinvar.tsv"))))
    db.insert_clingen_batch(list(parse_clingen(str(FIXTURES / "clingen.csv"))))
    return db


def _one(db, rsid, chrom, pos, genotype):
    [r] = analyze_variants([Variant(rsid, chrom, pos, genotype)], db)
    return r


class TestChallengeFixtures:
    """Each case in the synthetic fixture, end to end through analyze_variants."""

    def test_dominant_and_recessive_gene_resolves_per_assertion(self, challenge_db):
        recessive = _one(challenge_db, "rs9000001", "1", 1001, "GA")
        both = _one(challenge_db, "rs9000002", "1", 1002, "GA")
        dominant = _one(challenge_db, "rs9000003", "1", 1003, "GA")
        assert recessive.category == "Carrier Status" and recessive.inheritance == "autosomal recessive"
        assert both.category == "Health Conditions" and both.inheritance_resolution.status == "conflicting"
        assert dominant.category == "Health Conditions" and dominant.inheritance == "autosomal dominant"
        for r in (recessive, both, dominant):
            assert r.inheritance_resolution.gene_inheritance == "mixed (dominant and recessive conditions)"
        assert recessive.significance_rank == pytest.approx(dominant.significance_rank + CARRIER_RANK_SHIFT)

    def test_missing_identifiers_never_produce_a_carrier_label(self, challenge_db):
        r = _one(challenge_db, "rs9000004", "1", 1004, "GA")
        assert r.category == "Health Conditions"
        assert r.inheritance_resolution.status == "no_identifiers"
        assert r.inheritance == "unresolved (no condition identifiers)"
        assert "not provided" in r.inheritance_note and "gene-level: mixed" in r.inheritance_note

    def test_disputed_relationship_stays_unresolved(self, challenge_db):
        r = _one(challenge_db, "rs9000005", "1", 1005, "CT")
        assert r.category == "Health Conditions"
        assert r.inheritance_resolution.status == "not_established"
        assert r.inheritance == "not established (Disputed)"

    def test_multiple_recessive_conditions_all_visible(self, challenge_db):
        r = _one(challenge_db, "rs9000006", "1", 1006, "AG")
        assert r.category == "Carrier Status" and r.inheritance == "autosomal recessive"
        assert [e.disease for e in r.inheritance_resolution.matched] == [
            "SYNAR2 condition one", "SYNAR2 condition two",
        ]
        assert [c.mondo_id for c in r.inheritance_resolution.conditions] == ["MONDO:0900004", "MONDO:0900005"]

    def test_unambiguous_recessive_case(self, challenge_db):
        het = _one(challenge_db, "rs9000007", "1", 1007, "TC")
        hom = _one(challenge_db, "rs9000007", "1", 1007, "CC")
        assert het.category == "Carrier Status" and hom.category == "Health Conditions"
        assert het.inheritance_resolution.condition_id == "MONDO:0900006"
        assert het.inheritance_resolution.unmatched_condition_ids == []

    def test_curated_gene_but_uncurated_condition_is_unmapped(self, challenge_db):
        r = _one(challenge_db, "rs9000008", "1", 1008, "TC")
        assert r.category == "Health Conditions"
        assert r.inheritance_resolution.status == "unmapped"
        assert r.inheritance_resolution.unmatched_condition_ids == ["MONDO:0900099"]

    def test_x_linked_diploid_carrier(self, challenge_db):
        diploid = _one(challenge_db, "rs9000009", "X", 1009, "GA")
        hemizygous = _one(challenge_db, "rs9000009", "X", 1009, "A")
        assert diploid.category == "Carrier Status" and diploid.inheritance == "X-linked"
        assert hemizygous.category == "Health Conditions"

    def test_co_occurring_condition_entry_matches_its_curated_member(self, challenge_db):
        r = _one(challenge_db, "rs9000010", "1", 1010, "TC")
        assert r.category == "Carrier Status"
        assert [c.name for c in r.inheritance_resolution.conditions] == ["SYNAR condition", "Some feature"]

    def test_legacy_database_rows_read_not_stored(self, tmp_path):
        db = AllelioDB(str(tmp_path / "legacy.db"))
        db.initialize()
        db.cursor.execute("ALTER TABLE clinvar DROP COLUMN condition_ids")
        db.conn.commit()
        db.cursor.execute(
            "INSERT INTO clinvar (rsid, ref_allele, alt_allele, gene, clinical_significance, conditions, "
            "review_status, last_evaluated) VALUES ('rs9000007', 'T', 'C', 'SYNAR', 'Pathogenic', "
            "'SYNAR condition', 'criteria provided, single submitter', '')"
        )
        db.conn.commit()
        db.initialize()  # migrates: adds the column, leaves the legacy row NULL
        db.insert_clingen_batch(list(parse_clingen(str(FIXTURES / "clingen.csv"))))
        r = _one(db, "rs9000007", "1", 1007, "TC")
        assert r.category == "Health Conditions"
        assert r.inheritance_resolution.status == "identifiers_not_stored"
        assert "allelio update" in r.inheritance_note

    def test_every_surface_carries_the_same_resolution(self, challenge_db):
        from allelio.ai.prompts import build_variant_prompt
        from allelio.report import generate_html_report

        variants = [Variant("rs9000002", "1", 1002, "GA")]
        results = analyze_variants(variants, challenge_db)
        [r] = results
        document = build_evidence_export(results, variants, {}, stats=results.stats)
        finding = document["findings"][0]
        assert finding["inheritance"] == r.inheritance
        assert finding["inheritance_resolution"]["status"] == "conflicting"
        assert finding["inheritance_resolution"]["mapping"] == {"method": "mondo-exact", "version": "1.1"}
        assert finding["clinvar_entries"][0]["inheritance"]["status"] == "conflicting"
        assert finding["clinvar_entries"][0]["condition_ids"].startswith("MONDO:MONDO:0900001")
        json.dumps(document)
        prompt = build_variant_prompt(r)
        assert "conflicting (matched conditions differ" in prompt and "mondo-exact" in prompt
        html = generate_html_report(results, {}, "", {})
        assert "conflicting (matched conditions differ" in html and "mondo-exact" in html


def test_statuses_are_the_documented_set():
    assert {inh.RESOLVED, inh.CONFLICTING, inh.UNMAPPED, inh.NO_IDENTIFIERS, inh.NOT_STORED,
            inh.NOT_ESTABLISHED, inh.NOT_CURATED} == {
        "resolved", "conflicting", "unmapped", "no_identifiers", "identifiers_not_stored",
        "not_established", "not_curated",
    }
