"""Internal diagnostic evaluation of a separately frozen source-reference set.

Expected contracts are read from verified input artifacts, never fitted to the
production output. Row-level artifacts stay local; the report is aggregate only.
"""
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from allelio.clinvar_reference import SCENARIOS, sha256
from allelio.database.store import AllelioDB
from allelio.evidence import write_evidence_export
from allelio.runs import (code_identity, record_run, runtime_identity, annotation_checksum,
                          references, reference_identity)
from allelio.schema import validate_evidence


CHECKS = ("parsed", "filter_excluded", "source_allele_match", "source_alt_copies",
          "source_record_fidelity", "trace_contract", "observation_accounting", "row_disposition")
FIELDS = ("allele_id", "variation_id", "assembly", "chromosome", "position_vcf", "ref_allele",
          "alt_allele", "gene", "clinical_significance", "review_status")
OPTIONS = {"include_benign": True, "include_reference": True, "frequency_adjustment": False,
           "traits_only": False, "detailed_trace": True, "pgx_min_level": "2B"}
CLASSIFICATIONS = {"Pathogenic", "Likely pathogenic", "Pathogenic/Likely pathogenic", "Benign",
                   "Likely benign", "Benign/Likely benign", "Uncertain significance"}
REVIEWS = {"reviewed by expert panel", "practice guideline"}
ARTIFACTS = {"protocol.json", "records.jsonl", "cases.jsonl"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def local_bytes(root, name):
    path = root / name
    require(not path.is_symlink() and path.resolve().is_relative_to(root) and path.is_file(),
            "Frozen artifacts must be regular files inside the bundle.")
    return path.read_bytes()


def exact(left, right):
    return type(left) is type(right) and left == right


def valid_record(row):
    return (isinstance(row, dict) and re.fullmatch(r"rs[1-9][0-9]{0,18}", row.get("rsid", ""))
            and all(isinstance(row.get(key), str) and re.fullmatch(r"[1-9][0-9]{0,18}", row[key])
                    for key in ("allele_id", "variation_id"))
            and row.get("assembly") == "GRCh38" and row.get("chromosome") in {str(n) for n in range(1, 23)}
            and type(row.get("position")) is int and 0 < row["position"] < 2**63 - 1
            and row.get("ref") in {"A", "C", "G", "T"} and row.get("alt") in {"A", "C", "G", "T"}
            and row["ref"] != row["alt"] and isinstance(row.get("gene"), str)
            and isinstance(row.get("hgnc_id"), str) and row.get("germline_classification") in CLASSIFICATIONS
            and row.get("germline_review_status") in REVIEWS)


def load_set(bundle, trusted_manifest):
    root = Path(bundle).resolve()
    manifest_bytes = local_bytes(root, "manifest.json")
    trusted_bytes = Path(trusted_manifest).read_bytes()
    require(manifest_bytes == trusted_bytes, "Local manifest differs from the explicitly trusted manifest.")
    manifest = json.loads(manifest_bytes)
    require(manifest.get("schema") == "allelio-clinvar-reference-set/1"
            and manifest.get("evidence_type") == "internal_source_fidelity"
            and manifest.get("independent_validation") is False, "Unsupported reference-set scope.")
    require(set(manifest["artifacts"]) == ARTIFACTS, "Unexpected frozen artifact list.")
    raw = {name: local_bytes(root, name) for name in sorted(ARTIFACTS)}
    require(all(digest_bytes(raw[name]) == manifest["artifacts"][name] for name in ARTIFACTS),
            "Frozen artifact checksum mismatch.")
    source = manifest.get("source", {})
    require(isinstance(source.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", source["sha256"]),
            "A source checksum is required.")
    protocol = json.loads(raw["protocol.json"])
    require(protocol.get("schema") == "allelio-clinvar-reference-protocol/1"
            and protocol.get("source") == source and protocol.get("case_scenarios") == list(SCENARIOS),
            "Frozen protocol and set manifest disagree.")
    records = [json.loads(line) for line in raw["records.jsonl"].splitlines()]
    require(bool(records) and all(valid_record(row) for row in records), "Invalid selected reference record.")
    by_rsid = {row["rsid"]: row for row in records}
    selection_counts = manifest["selection_counts"]
    numeric_counts = [value for key, value in selection_counts.items() if key != "first_rule_exclusions"]
    numeric_counts.extend(selection_counts["first_rule_exclusions"].values())
    require(all(type(value) is int and value >= 0 for value in numeric_counts), "Invalid source count types.")
    require(len(by_rsid) == len(records) == manifest["selection_counts"]["selected_records"],
            "Missing or duplicate reference records.")
    expected_strata = {key: dict(Counter(row[key] for row in records)) for key in
                       ("germline_classification", "germline_review_status", "chromosome")}
    require(expected_strata == manifest["strata"], "Reference strata disagree with the frozen manifest.")
    grouped, seen = {name: [] for name in SCENARIOS}, set()
    for line in raw["cases.jsonl"].splitlines():
        case = json.loads(line)
        require(isinstance(case, dict) and set(case) == {"id", "record_rsid", "scenario", "input", "expected"},
                "Invalid case shape.")
        rsid, scenario = case["record_rsid"], case["scenario"]
        require(rsid in by_rsid and scenario in grouped and case["id"] == rsid + "-" + scenario
                and case["id"] not in seen, "Unknown, missing, or duplicate case identity.")
        seen.add(case["id"])
        value, expected = case["input"], case["expected"]
        require(isinstance(value, dict) and set(value) == {"reference_declaration", "chromosome", "position",
                "rsid", "ref", "alt", "filter", "gt"}, "Invalid VCF input shape.")
        require(value["rsid"] == rsid and value["chromosome"] in {str(n) for n in range(1, 23)}
                and type(value["position"]) is int and 0 < value["position"] < 2**63
                and value["ref"] in {"A", "C", "G", "T"} and value["alt"] in {"A", "C", "G", "T"}
                and value["ref"] != value["alt"] and value["reference_declaration"] in (None, "GRCh37", "GRCh38")
                and value["filter"] in ("PASS", "q10") and value["gt"] in ("0/0", "0/1", "1/1", "./."),
                "Unsupported VCF input contract.")
        require(isinstance(expected, dict) and set(expected) == set(CHECKS[:4])
                and type(expected["parsed"]) is bool and type(expected["filter_excluded"]) is bool
                and expected["source_allele_match"] in ("carried", "absent", "unknown", "not_evaluated")
                and (expected["source_alt_copies"] is None or
                     (type(expected["source_alt_copies"]) is int and expected["source_alt_copies"] in (0, 1, 2))),
                "Invalid expected contract types.")
        grouped[scenario].append(case)
    require(all(len(cases) == len(records) and {c["record_rsid"] for c in cases} == set(by_rsid)
                for cases in grouped.values()), "Every record requires exactly nine distinct scenarios.")
    counts = {name: len(cases) for name, cases in grouped.items()}
    require(type(manifest["case_counts"]["total"]) is int
            and all(type(value) is int for value in manifest["case_counts"]["by_scenario"].values()),
            "Invalid case count types.")
    require(counts == manifest["case_counts"]["by_scenario"] and sum(counts.values()) == manifest["case_counts"]["total"],
            "Case counts disagree with the frozen manifest.")
    return manifest, by_rsid, grouped, digest_bytes(manifest_bytes)


def database_record(row):
    """Bridge selected structured fields; this does not run the TSV importer."""
    return {"rsid": row["rsid"], "allele_id": row["allele_id"], "variation_id": row["variation_id"],
            "assembly": row["assembly"], "chromosome": row["chromosome"], "position_vcf": row["position"],
            "ref_allele": row["ref"], "alt_allele": row["alt"], "gene": row["gene"], "hgnc_id": row["hgnc_id"],
            "clinical_significance": row["germline_classification"], "review_status": row["germline_review_status"],
            "classification_type": "germline"}


def expected_identity(row):
    return {"allele_id": row["allele_id"], "variation_id": row["variation_id"], "assembly": "GRCh38",
            "chromosome": row["chromosome"], "position_vcf": row["position"], "ref_allele": row["ref"],
            "alt_allele": row["alt"], "gene": row["gene"], "clinical_significance": row["germline_classification"],
            "review_status": row["germline_review_status"]}


def write_vcf(cases, path):
    declaration = cases[0]["input"]["reference_declaration"]
    require(all(case["input"]["reference_declaration"] == declaration for case in cases),
            "A scenario batch must have one reference declaration.")
    lines = ["##fileformat=VCFv4.2", "##source=Allelio_constructed_reference_cases"]
    if declaration is not None:
        lines.append("##reference=" + declaration)
    lines.append("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSYNTHETIC_CONSTRUCTED")
    row_map = {}
    for case in cases:
        value = case["input"]
        lines.append("\t".join(str(value[key]) for key in ("chromosome", "position", "rsid", "ref", "alt"))
                     + "\t.\t" + value["filter"] + "\t.\tGT\t" + value["gt"])
        row_map[case["id"]] = len(lines)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return row_map


def index_outputs(evidence, cases, row_map):
    indexes = {name: defaultdict(list) for name in ("inputs", "coverage", "findings", "candidates")}
    for row in evidence["inputs"]:
        indexes["inputs"][row.get("source_line")].append(row)
    for row in evidence["coverage"]["rows"]:
        indexes["coverage"][row.get("line")].append(row)
    for row in evidence["findings"]:
        indexes["findings"][row.get("rsid")].append(row)
    for row in evidence["matching"]["candidates"]:
        indexes["candidates"][row.get("rsid")].append(row)
    allowed_lines, allowed_rsids = set(row_map.values()), {case["record_rsid"] for case in cases}
    extras = {name: sum(len(rows) for key, rows in index.items()
                        if key not in (allowed_lines if name in ("inputs", "coverage") else allowed_rsids))
              for name, index in indexes.items()}
    accounted = (evidence["coverage"]["complete"] is True
                 and evidence["coverage"]["total_rows"] == len(cases)
                 and evidence["coverage"]["accounted_rows"] == len(cases) and not any(extras.values()))
    return indexes, {"accounted": accounted, "unexpected_outputs": extras}


def score_case(case, row, line, indexes, protocol):
    rsid, scenario = case["record_rsid"], case["scenario"]
    inputs, coverage = indexes["inputs"][line], indexes["coverage"][line]
    findings, candidates = indexes["findings"][rsid], indexes["candidates"][rsid]
    disposition = coverage[0].get("status") if len(coverage) == 1 else "missing_or_duplicate"
    parsed = len(inputs) == 1 and inputs[0].get("rsid") == rsid
    entries = findings[0].get("clinvar_entries", []) if len(findings) == 1 else []
    excluded = disposition == "failed_filter"
    no_call = disposition == "no_call"
    match = entries[0].get("allele_match") if len(entries) == 1 else (
        "not_evaluated" if (excluded or no_call) and not findings else "missing_or_duplicate")
    copies = findings[0].get("alt_copies", "missing") if len(findings) == 1 else (
        None if (excluded or no_call) and not findings else "missing")
    observed = {"parsed": parsed, "filter_excluded": excluded,
                "source_allele_match": match, "source_alt_copies": copies}
    checks = {key: exact(value, observed[key]) for key, value in case["expected"].items()}
    applicable = scenario != "no_call"  # fixed before observing whether outputs exist
    identity = candidates[0].get("identity", {}) if len(candidates) == 1 else {}
    checks["source_record_fidelity"] = (all(exact(identity.get(key), value) for key, value in expected_identity(row).items())
                                           if applicable else None)
    if applicable and scenario != "failed_filter":
        checks["source_record_fidelity"] = (checks["source_record_fidelity"] and len(entries) == 1
            and all(exact(entries[0].get(key), value) for key, value in expected_identity(row).items()))
    trace = [candidates[0].get(key) for key in ("decision", "stage", "reason")] if len(candidates) == 1 else None
    checks["trace_contract"] = (trace == protocol["trace_contracts"][scenario]
                                and (not candidates if not applicable else len(candidates) == 1 and candidates[0].get("source") == "clinvar"))
    expected_findings = 0 if scenario in ("no_call", "failed_filter") else 1
    checks["observation_accounting"] = (len(inputs) == int(case["expected"]["parsed"])
        and len(coverage) == 1 and len(findings) == expected_findings
        and len(candidates) == int(applicable) and len(entries) == expected_findings
        and all(value.get("rsid") == rsid for value in inputs)
        and all(value.get("rsid") == rsid for value in entries))
    checks["row_disposition"] = disposition == ("no_call" if scenario == "no_call" else
                                                "failed_filter" if scenario == "failed_filter" else "reported")
    return {"case_id": case["id"], "record_rsid": rsid, "scenario": scenario, "expected": case["expected"],
            "observed": {**observed, "row_disposition": disposition, "trace": trace}, "checks": checks,
            "passed": all(value is True for value in checks.values() if value is not None)}


def public_runtime():
    """Export only bounded dependency/runtime versions, never arbitrary metadata."""
    identity = runtime_identity()
    def version(value):
        return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._+\-]{1,100}", value) else None
    return {**{key: version(identity.get(key)) for key in ("python", "implementation", "sqlite")},
            "packages": {key: version(identity.get("packages", {}).get(key))
                         for key in ("click", "jsonschema", "httpx", "ollama")}}


def evaluate_reference_set(bundle, trusted_manifest, evaluation_protocol, output):
    root, output = Path(bundle).resolve(), Path(output).resolve()
    require(not output.exists() and not output.is_relative_to(root), "Use a new output directory outside the frozen bundle.")
    manifest, records, grouped, manifest_hash = load_set(root, trusted_manifest)
    protocol_bytes = Path(evaluation_protocol).read_bytes()
    protocol = json.loads(protocol_bytes)
    require(protocol.get("schema") == "allelio-clinvar-reference-evaluation-protocol/1"
            and protocol.get("checks") == list(CHECKS) and protocol.get("source_fidelity_fields") == list(FIELDS)
            and protocol.get("annotation_options") == OPTIONS
            and all(exact(protocol["annotation_options"][key], value) for key, value in OPTIONS.items())
            and set(protocol.get("trace_contracts", {})) == set(SCENARIOS), "Unsupported evaluation protocol.")
    software = code_identity()
    output.mkdir(parents=True)
    (output / "INCOMPLETE").write_text("No completed report exists until final integrity checks succeed.\n")
    (output / "evaluation-protocol.json").write_bytes(protocol_bytes)
    db = AllelioDB(str(output / "references.db"))
    try:
        db.initialize()
        db.insert_clinvar_batch([database_record(row) for row in records.values()])
        db.set_metadata("clinvar_release", manifest["source"]["snapshot_date"])
        db.set_metadata("clinvar_sha256", manifest["source"]["sha256"])
    finally:
        db.close()
    with references(output / "references.db") as frozen_db:
        reference_fingerprint = reference_identity(frozen_db)
    metrics = {name: {"cases": 0, "passed": 0, "failed": 0, "checks": {key: Counter() for key in CHECKS}} for name in SCENARIOS}
    cluster_pass = {rsid: True for rsid in records}
    batches, strata = {}, {key: defaultdict(Counter) for key in ("germline_classification", "germline_review_status")}
    emitted_results = hashlib.sha256()
    with (output / "case-results.jsonl").open("wb") as results_file:
        for scenario, cases in grouped.items():
            batch = output / scenario
            batch.mkdir()
            row_map = write_vcf(cases, batch / "input.vcf")
            run, evidence, _ = record_run(batch / "input.vcf", output / "references.db", options=OPTIONS, explain=False)
            require(run["references"] == reference_fingerprint and run["software"] == software
                    and run["input"]["sha256"] == sha256(batch / "input.vcf")
                    and run["annotation_sha256"] == annotation_checksum(evidence),
                    "Batch evidence does not match the recorded execution.")
            write_evidence_export(run, batch / "run.json")
            write_evidence_export(evidence, batch / "evidence.json")
            evidence_errors = validate_evidence(evidence)
            write_evidence_export({"errors": evidence_errors}, batch / "validation-errors.json")
            indexes, integrity = index_outputs(evidence, cases, row_map)
            integrity.update(evidence_contract_valid=not evidence_errors, evidence_contract_errors=len(evidence_errors))
            integrity["accounted"] &= not evidence_errors
            for case in cases:
                result = score_case(case, records[case["record_rsid"]], row_map[case["id"]], indexes, protocol)
                serialized = (json.dumps(result, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
                results_file.write(serialized)
                emitted_results.update(serialized)
                group = metrics[scenario]
                group["cases"] += 1
                group["passed" if result["passed"] else "failed"] += 1
                cluster_pass[case["record_rsid"]] &= result["passed"]
                for key, value in result["checks"].items():
                    group["checks"][key]["not_applicable" if value is None else "passed" if value else "failed"] += 1
                for key in strata:
                    strata[key][records[case["record_rsid"]][key]]["passed" if result["passed"] else "failed"] += 1
            batches[scenario] = {**integrity, "input_sha256": sha256(batch / "input.vcf"),
                                 "evidence_sha256": sha256(batch / "evidence.json"),
                                 "annotation_sha256": annotation_checksum(evidence), "run_sha256": sha256(batch / "run.json"),
                                 "validation_errors_sha256": sha256(batch / "validation-errors.json")}
    # Reject ordinary mid-run mutation without producing a completed public report.
    require(sha256(output / "case-results.jsonl") == emitted_results.hexdigest()
            and (output / "evaluation-protocol.json").read_bytes() == protocol_bytes,
            "Retained case results or execution protocol changed during execution.")
    require(load_set(root, trusted_manifest)[3] == manifest_hash and code_identity() == software
            and Path(evaluation_protocol).read_bytes() == protocol_bytes, "Evaluation inputs or software changed during execution.")
    with references(output / "references.db") as frozen_db:
        require(reference_identity(frozen_db) == reference_fingerprint, "Reference contents changed during execution.")
    for scenario, hashes in batches.items():
        require(all(sha256(output / scenario / name) == hashes[key] for name, key in
                    (("input.vcf", "input_sha256"), ("evidence.json", "evidence_sha256"), ("run.json", "run_sha256"),
                     ("validation-errors.json", "validation_errors_sha256"))),
                "Local batch artifacts changed during execution.")
    report = {"schema": "allelio-clinvar-reference-evaluation/1", "status": "complete",
              "evidence_type": "internal_source_fidelity", "independent_validation": False,
              "software": software, "runtime": public_runtime(), "adapter_sha256": sha256(__file__),
              "references_logical_sha256": reference_fingerprint["logical_sha256"],
              "set_manifest_sha256": manifest_hash, "source_sha256": manifest["source"]["sha256"],
              "evaluation_protocol_sha256": digest_bytes(protocol_bytes), "annotation_options": dict(OPTIONS),
              "cases": {"total": sum(group["cases"] for group in metrics.values()),
                        "passed": sum(group["passed"] for group in metrics.values()),
                        "failed": sum(group["failed"] for group in metrics.values())},
              "source_record_clusters": {"total": len(records), "all_cases_passed": sum(cluster_pass.values())},
              "by_scenario": {name: {**group, "checks": {key: {"opportunities": group["cases"] - counts["not_applicable"],
                  "passed": counts["passed"], "failed": counts["failed"], "not_applicable": counts["not_applicable"]}
                  for key, counts in group["checks"].items()}} for name, group in metrics.items()},
              "by_source_stratum": {key: {name: dict(counts) for name, counts in groups.items()} for key, groups in strata.items()},
              "batches": batches, "case_results_sha256": emitted_results.hexdigest(),
              "source_fidelity_fields": list(FIELDS),
              "limitations": ["Internal contracts over constructed cases, not independent biological samples or clinical accuracy.",
                  "Nine cases per selected source record are paired and clustered; no independence-based intervals are reported.",
                  "Minimal ClinVar-only database loading bypasses the production TSV importer and all other reference sources.",
                  "Source-field checks measure selected-record to database to lookup/export round-trip fidelity; HGNC ID is not measured.",
                  "Diagnostic include_reference/include_benign options differ from default reporting; ranking and report usefulness are not evaluated.",
                  "No models, model discovery, reference downloads, real participant data, or clinical interpretations are used.",
                  "Full row-level artifacts remain local; this report contains aggregate measurements and provenance hashes."]}
    report["passed"] = (report["cases"]["failed"] == 0 and all(batch["accounted"] for batch in batches.values()))
    write_evidence_export(report, output / "report.pending.json")
    (output / "INCOMPLETE").unlink()
    (output / "report.pending.json").replace(output / "report.json")
    return report
