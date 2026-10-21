"""Adapter integrity and observed-outcome checks on invented source records only."""
import copy
import gzip
import json
import socket
from pathlib import Path

import pytest

from allelio import reference_evaluation as evaluation
from allelio.clinvar_reference import REQUIRED, build_reference_set, sha256


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "data/evaluation/clinvar-reference-evaluation-v1.protocol.json"


def fixture_set(tmp_path):
    source = tmp_path / "invented.tsv.gz"
    row = {key: "-" for key in REQUIRED}
    row.update({"#AlleleID": "800000001", "Type": "single nucleotide variant", "GeneSymbol": "SYNTHETIC",
                "ClinicalSignificance": "Benign", "RS# (dbSNP)": "800000001", "Assembly": "GRCh38",
                "Chromosome": "1", "ReviewStatus": "reviewed by expert panel", "VariationID": "800000001",
                "PositionVCF": "100", "ReferenceAlleleVCF": "A", "AlternateAlleleVCF": "G"})
    header = sorted(REQUIRED)
    with gzip.open(source, "wt", encoding="utf-8") as stream:
        stream.write("\t".join(header) + "\n" + "\t".join(row[key] for key in header) + "\n")
    protocol = tmp_path / "source-protocol.json"
    definition = json.loads((ROOT / "data/evaluation/clinvar-reference-v1.protocol.json").read_text())
    definition["source"]["sha256"] = sha256(source)
    definition["rights_review"]["private_note"] = "PRIVATE_SOURCE_METADATA_SENTINEL"
    protocol.write_text(json.dumps(definition))
    bundle = tmp_path / "bundle"
    build_reference_set(source, protocol, bundle)
    trusted = tmp_path / "trusted.json"
    trusted.write_bytes((bundle / "manifest.json").read_bytes())
    return bundle, trusted


def reanchor(bundle, trusted, artifact):
    """Tests may explicitly trust a modified set to exercise structural checks."""
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["artifacts"][artifact] = sha256(bundle / artifact)
    value = json.dumps(manifest, sort_keys=True)
    (bundle / "manifest.json").write_text(value)
    trusted.write_text(value)


def test_actual_pipeline_contracts_and_public_summary_without_network_or_models(tmp_path, monkeypatch):
    bundle, trusted = fixture_set(tmp_path)
    before = {name: sha256(bundle / name) for name in ("manifest.json", "protocol.json", "cases.jsonl", "records.jsonl")}
    def deny(*args, **kwargs):
        raise AssertionError("The reference adapter must not contact network or AI.")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    from allelio.ai.engine import AIEngine
    monkeypatch.setattr(AIEngine, "__init__", deny)
    output = tmp_path / "result"
    report = evaluation.evaluate_reference_set(bundle, trusted, PROTOCOL, output)
    assert report["passed"] is True
    assert report["cases"] == {"total": 9, "passed": 9, "failed": 0}
    assert report["source_record_clusters"] == {"total": 1, "all_cases_passed": 1}
    assert not (output / "INCOMPLETE").exists()
    assert all(sha256(bundle / name) == value for name, value in before.items())
    assert report["by_scenario"]["no_call"]["checks"]["source_record_fidelity"] == {
        "opportunities": 0, "passed": 0, "failed": 0, "not_applicable": 1}
    assert report["by_scenario"]["failed_filter"]["checks"]["source_record_fidelity"]["opportunities"] == 1
    local = [json.loads(line) for line in (output / "case-results.jsonl").read_text().splitlines()]
    assert local[0]["observed"]["source_alt_copies"] == 0
    assert local[1]["observed"]["source_alt_copies"] == 1
    assert local[2]["observed"]["source_alt_copies"] == 2
    public_text = (output / "report.json").read_text()
    assert "PRIVATE_SOURCE_METADATA_SENTINEL" not in public_text
    assert str(tmp_path) not in public_text
    assert "rs800000001" not in public_text
    assert "SYNTHETIC_CONSTRUCTED" not in public_text


def test_missing_output_is_failure_without_shrinking_applicability(tmp_path, monkeypatch):
    bundle, trusted = fixture_set(tmp_path)
    original = evaluation.record_run
    def missing(file, *args, **kwargs):
        run, evidence, explanations = original(file, *args, **kwargs)
        if file.parent.name == "heterozygous":
            evidence["findings"] = []
            run["annotation_sha256"] = evaluation.annotation_checksum(evidence)
        return run, evidence, explanations
    monkeypatch.setattr(evaluation, "record_run", missing)
    report = evaluation.evaluate_reference_set(bundle, trusted, PROTOCOL, tmp_path / "result")
    assert report["passed"] is False
    assert report["cases"] == {"total": 9, "passed": 8, "failed": 1}
    checks = report["by_scenario"]["heterozygous"]["checks"]
    assert checks["source_alt_copies"] == {"opportunities": 1, "passed": 0, "failed": 1, "not_applicable": 0}
    assert checks["source_record_fidelity"]["opportunities"] == 1
    assert checks["observation_accounting"]["failed"] == 1


def test_extra_foreign_outputs_fail_batch_without_echoing_them(tmp_path, monkeypatch):
    bundle, trusted = fixture_set(tmp_path)
    original = evaluation.record_run
    def extra(file, *args, **kwargs):
        run, evidence, explanations = original(file, *args, **kwargs)
        if file.parent.name == "reference":
            value = copy.deepcopy(evidence["matching"]["candidates"][0])
            value["rsid"] = "PRIVATE_OUTPUT_SENTINEL"
            evidence["matching"]["candidates"].append(value)
            run["annotation_sha256"] = evaluation.annotation_checksum(evidence)
        return run, evidence, explanations
    monkeypatch.setattr(evaluation, "record_run", extra)
    output = tmp_path / "result"
    report = evaluation.evaluate_reference_set(bundle, trusted, PROTOCOL, output)
    assert report["passed"] is False
    assert report["batches"]["reference"]["unexpected_outputs"]["candidates"] == 1
    assert "PRIVATE_OUTPUT_SENTINEL" not in (output / "report.json").read_text()


def test_invalid_evidence_links_fail_overall_even_when_case_contracts_match(tmp_path, monkeypatch):
    bundle, trusted = fixture_set(tmp_path)
    original = evaluation.record_run
    def invalid_link(file, *args, **kwargs):
        run, evidence, explanations = original(file, *args, **kwargs)
        if file.parent.name == "heterozygous":
            evidence["findings"][0]["input_ids"] = ["FOREIGN_DOCUMENT_ID"]
            run["annotation_sha256"] = evaluation.annotation_checksum(evidence)
        return run, evidence, explanations
    monkeypatch.setattr(evaluation, "record_run", invalid_link)
    output = tmp_path / "result"
    report = evaluation.evaluate_reference_set(bundle, trusted, PROTOCOL, output)
    assert report["passed"] is False
    assert report["cases"]["passed"] == 9
    assert report["batches"]["heterozygous"]["evidence_contract_valid"] is False
    assert report["batches"]["heterozygous"]["evidence_contract_errors"] > 0
    assert "FOREIGN_DOCUMENT_ID" not in (output / "report.json").read_text()
    assert "FOREIGN_DOCUMENT_ID" in (output / "heterozygous/validation-errors.json").read_text()


def test_returned_source_fields_must_match_even_if_trace_is_correct(tmp_path, monkeypatch):
    bundle, trusted = fixture_set(tmp_path)
    original = evaluation.record_run
    def wrong_label(file, *args, **kwargs):
        run, evidence, explanations = original(file, *args, **kwargs)
        if file.parent.name == "heterozygous":
            evidence["findings"][0]["clinvar_entries"][0]["clinical_significance"] = "Pathogenic"
            run["annotation_sha256"] = evaluation.annotation_checksum(evidence)
        return run, evidence, explanations
    monkeypatch.setattr(evaluation, "record_run", wrong_label)
    report = evaluation.evaluate_reference_set(bundle, trusted, PROTOCOL, tmp_path / "result")
    assert report["passed"] is False
    assert report["by_scenario"]["heterozygous"]["checks"]["source_record_fidelity"]["failed"] == 1


@pytest.mark.parametrize("artifact", ["protocol", "case_results"])
def test_retained_scoring_artifact_mutation_prevents_completion(tmp_path, monkeypatch, artifact):
    bundle, trusted = fixture_set(tmp_path)
    original = evaluation.record_run
    output = tmp_path / "result"
    def mutate_copy(file, *args, **kwargs):
        value = original(file, *args, **kwargs)
        if file.parent.name == "no_call":
            if artifact == "protocol":
                (output / "evaluation-protocol.json").write_bytes(b"changed")
            else:
                with (output / "case-results.jsonl").open("ab") as stream:
                    stream.write(b"UNSCORED_BYTES" * 8192)
        return value
    monkeypatch.setattr(evaluation, "record_run", mutate_copy)
    with pytest.raises(ValueError, match="Retained case results"):
        evaluation.evaluate_reference_set(bundle, trusted, PROTOCOL, output)
    assert (output / "INCOMPLETE").is_file()
    assert not (output / "report.json").exists()


@pytest.mark.parametrize("change", ["hash", "duplicate", "missing", "boolean"])
def test_tampered_or_incomplete_sets_fail_before_output(tmp_path, change):
    bundle, trusted = fixture_set(tmp_path)
    path = bundle / "cases.jsonl"
    lines = path.read_text().splitlines()
    if change in ("hash", "duplicate"):
        lines.append(lines[0])
    elif change == "missing":
        lines.pop()
    else:
        value = json.loads(lines[1])
        value["expected"]["source_alt_copies"] = True
        lines[1] = json.dumps(value)
    path.write_text("\n".join(lines) + "\n")
    if change != "hash":
        reanchor(bundle, trusted, "cases.jsonl")
    output = tmp_path / "result"
    with pytest.raises(ValueError):
        evaluation.evaluate_reference_set(bundle, trusted, PROTOCOL, output)
    assert not output.exists()


def test_symlink_overlap_and_clobber_rejected(tmp_path):
    bundle, trusted = fixture_set(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        evaluation.evaluate_reference_set(bundle, trusted, PROTOCOL, bundle / "output")
    with pytest.raises(ValueError, match="new output"):
        evaluation.evaluate_reference_set(bundle, trusted, PROTOCOL, tmp_path)
    protocol = bundle / "protocol.json"
    outside = tmp_path / "protocol-copy.json"
    outside.write_bytes(protocol.read_bytes())
    protocol.unlink()
    protocol.symlink_to(outside)
    with pytest.raises(ValueError, match="regular files"):
        evaluation.evaluate_reference_set(bundle, trusted, PROTOCOL, tmp_path / "result")


def test_mid_run_set_mutation_leaves_incomplete_output(tmp_path, monkeypatch):
    bundle, trusted = fixture_set(tmp_path)
    original = evaluation.record_run
    def mutate(file, *args, **kwargs):
        value = original(file, *args, **kwargs)
        if file.parent.name == "no_call":
            with (bundle / "cases.jsonl").open("a") as stream:
                stream.write("modified")
        return value
    monkeypatch.setattr(evaluation, "record_run", mutate)
    output = tmp_path / "result"
    with pytest.raises(ValueError, match="checksum"):
        evaluation.evaluate_reference_set(bundle, trusted, PROTOCOL, output)
    assert (output / "INCOMPLETE").is_file()
    assert not (output / "report.json").exists()
