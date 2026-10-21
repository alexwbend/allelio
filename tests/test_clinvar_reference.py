"""Invented source rows exercise reference-set boundaries, not clinical validity."""
import gzip
import json
from pathlib import Path

import pytest

from allelio.clinvar_reference import REQUIRED, build_reference_set, sha256


PROTOCOL = Path(__file__).resolve().parents[1] / "data/evaluation/clinvar-reference-v1.protocol.json"


def row(rsid="800000001", **changes):
    value = {key: "-" for key in REQUIRED}
    value.update({"#AlleleID": rsid, "Type": "single nucleotide variant", "GeneSymbol": "SYNTHETIC",
                  "ClinicalSignificance": "Benign", "RS# (dbSNP)": rsid, "Assembly": "GRCh38",
                  "Chromosome": "1", "ReviewStatus": "reviewed by expert panel", "VariationID": rsid,
                  "PositionVCF": "100", "ReferenceAlleleVCF": "A", "AlternateAlleleVCF": "G"})
    value.update(changes)
    return value


def prepare(tmp_path, records, header=None):
    source = tmp_path / "invented.tsv.gz"
    header = header or sorted(REQUIRED)
    with gzip.open(source, "wt", encoding="utf-8") as stream:
        stream.write("\t".join(header) + "\n")
        for record in records:
            stream.write("\t".join(record.get(key, "-") for key in header) + "\n")
    protocol = json.loads(PROTOCOL.read_text())
    protocol["source"].update(sha256=sha256(source), name="invented test fixture", snapshot_mirror=None)
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol))
    return source, path


def test_frozen_artifacts_have_exact_source_expectations_and_no_local_paths(tmp_path):
    source, protocol = prepare(tmp_path, [row(), row("800000002", ReviewStatus="practice guideline",
                                                  ClinicalSignificance="Pathogenic", PositionVCF="200")])
    output = tmp_path / "one"
    result = build_reference_set(source, protocol, output)
    assert result["selection_counts"]["selected_records"] == 2
    assert result["strata"]["germline_classification"] == {"Benign": 1, "Pathogenic": 1}
    assert result["case_counts"]["total"] == 18
    cases = {case["id"]: case for case in map(json.loads, (output / "cases.jsonl").read_text().splitlines())}
    for scenario, copies in (("reference", 0), ("heterozygous", 1), ("alternate", 2)):
        assert cases["rs800000001-" + scenario]["expected"]["source_alt_copies"] == copies
    for scenario in ("unknown_build", "wrong_build", "wrong_position", "wrong_allele"):
        assert cases["rs800000001-" + scenario]["expected"] == {
            "parsed": True, "filter_excluded": False, "source_allele_match": "unknown", "source_alt_copies": None}
    assert cases["rs800000001-no_call"]["expected"]["parsed"] is False
    assert cases["rs800000001-failed_filter"]["expected"]["filter_excluded"] is True
    assert cases["rs800000001-wrong_allele"]["input"]["alt"] == "C"
    assert cases["rs800000001-unknown_build"]["input"]["reference_declaration"] is None
    assert result["independent_validation"] is False
    assert str(tmp_path) not in (output / "manifest.json").read_text()
    for name, digest in result["artifacts"].items():
        assert sha256(output / name) == digest
    second = build_reference_set(source, protocol, tmp_path / "two")
    assert second == result


def test_somatic_stars_and_other_source_alleles_do_not_qualify(tmp_path):
    source, protocol = prepare(tmp_path, [row(), row("800000002", ReviewStatus="criteria provided, single submitter",
                                                  ReviewStatusClinicalImpact="practice guideline"),
                                         row("800000003"), row("800000003", ReviewStatus="criteria provided, single submitter",
                                                               AlternateAlleleVCF="C"),
                                         row("800000004", ReferenceAlleleVCF="G"),
                                         row("800000005", Chromosome="X"),
                                         row("800000006", ClinicalSignificance="no classification for the single variant")])
    result = build_reference_set(source, protocol, tmp_path / "set")
    counts = result["selection_counts"]
    assert counts["source_rows"] == 7
    assert counts["eligible_source_rows"] == 2
    assert counts["ambiguous_eligible_rows"] == counts["ambiguous_rsids"] == 1
    assert counts["selected_records"] == 1
    assert sum(counts["first_rule_exclusions"].values()) + counts["eligible_source_rows"] == 7
    assert result["strata"]["germline_classification"] == {"Benign": 1}


def test_duplicates_are_excluded_even_with_same_source_identity(tmp_path):
    source, protocol = prepare(tmp_path, [row(), row("800000002"), row("800000002")])
    result = build_reference_set(source, protocol, tmp_path / "set")
    assert result["selection_counts"]["selected_records"] == 1
    assert result["selection_counts"]["ambiguous_eligible_rows"] == 2


def test_bad_hash_old_header_and_existing_output_fail_without_overwrite(tmp_path):
    source, protocol = prepare(tmp_path, [row()])
    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="checksum"):
        build_reference_set(source, protocol, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()
    source, protocol = prepare(tmp_path, [row()], header=sorted(REQUIRED - {"SomaticClinicalImpact"}))
    with pytest.raises(ValueError, match="post-split"):
        build_reference_set(source, protocol, tmp_path / "old")
    source, protocol = prepare(tmp_path, [row()])
    existing = tmp_path / "existing"
    existing.mkdir()
    marker = existing / "marker"
    marker.write_text("preserve")
    with pytest.raises(ValueError, match="never overwritten"):
        build_reference_set(source, protocol, existing)
    assert marker.read_text() == "preserve"


def test_header_reordering_is_independent_of_production_column_positions(tmp_path):
    source, protocol = prepare(tmp_path, [row()], header=sorted(REQUIRED, reverse=True))
    result = build_reference_set(source, protocol, tmp_path / "set")
    assert result["selection_counts"]["selected_records"] == 1


def test_changed_source_during_selection_does_not_create_a_frozen_set(tmp_path, monkeypatch):
    from allelio import clinvar_reference
    source, protocol = prepare(tmp_path, [row()])
    original = clinvar_reference.rows
    calls = []

    def change_after_read(path):
        yield from original(path)
        calls.append(True)
        if len(calls) == 2:
            with source.open("ab") as stream:
                stream.write(b"changed")

    monkeypatch.setattr(clinvar_reference, "rows", change_after_read)
    with pytest.raises(ValueError, match="Source changed"):
        build_reference_set(source, protocol, tmp_path / "set")
    assert not (tmp_path / "set").exists()
