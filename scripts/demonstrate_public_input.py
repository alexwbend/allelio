#!/usr/bin/env python3
"""Run a pinned public research input locally; emit only aggregate metrics."""
import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from allelio.evidence import write_evidence_export
from allelio.reference_evaluation import public_runtime
from allelio.runs import (OPTIONS, annotation_checksum, checksum, code_identity,
                          record_run, reference_identity, references, replay_run)
from allelio.schema import validate_evidence

PROTOCOL = ROOT / "data/evaluation/giab-input-v1.protocol.json"
STATUSES = {"malformed_row", "invalid_position", "unsupported_identifier", "missing_genotype",
            "no_call", "unsupported_genotype", "parsed", "conflicting_input", "no_annotation",
            "failed_filter", "reference_or_no_applicable_annotation", "rank_filtered", "reported",
            "report_filtered", "duplicate_row", "unaccounted"}


def require(condition):
    if not condition:
        raise ValueError("Public-input contract failed; inspect retained local artifacts.")


def outside_checkout(path):
    path = Path(path).resolve()
    require(not any((parent / ".git").exists() for parent in (path, *path.parents)))
    return path


def fingerprints(path):
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(block)
            md5.update(block)
    return {"sha256": sha.hexdigest(), "md5": md5.hexdigest()}


def select_rows(source, target, selection):
    """Stream the whole source; preserve bytes, not rewritten VCF fields."""
    total, selected, headers = 0, 0, 0
    identifier_counts = Counter({"missing": 0, "rsid_syntax": 0, "other": 0})
    header_seen, data_seen = False, False
    emitted = hashlib.sha256()
    with gzip.open(source, "rb") as incoming, target.open("xb") as outgoing:
        for line in incoming:
            if line.startswith(b"#"):
                require(not data_seen)
                if line.startswith(b"#CHROM\t"):
                    require(not header_seen and len(line.rstrip(b"\r\n").split(b"\t")) == 10)
                    header_seen = True  # exactly one sample, kept locally
                outgoing.write(line)
                emitted.update(line)
                headers += 1
                continue
            if not line.strip():
                continue
            data_seen = True
            require(header_seen)
            columns = line.rstrip(b"\r\n").split(b"\t")
            require(len(columns) == 10)
            contig = columns[0].decode("ascii")
            position = int(columns[1])
            require(position > 0)
            total += 1
            if contig in selection["contig_aliases"] and selection["start_1based_inclusive"] <= position <= selection["end_1based_inclusive"]:
                selected += 1
                require(selected <= selection["maximum_selected_rows"])
                outgoing.write(line)
                emitted.update(line)
                value = columns[2]
                identifier_counts["missing" if value in (b"", b".") else
                                  "rsid_syntax" if re.fullmatch(rb"rs[0-9]+", value) else "other"] += 1
    require(header_seen and selected > 0)
    return {"source_rows_scanned": total, "selected_rows": selected,
            "header_lines_retained": headers, "selected_identifier_syntax": dict(identifier_counts)}, emitted.hexdigest()


def no_network(*args, **kwargs):
    raise RuntimeError("Network access is disabled for this demonstration.")


@contextmanager
def private_log(path):
    with path.open("x") as log, redirect_stdout(log), redirect_stderr(log):
        try:
            yield
        except Exception:
            traceback.print_exc(file=log)
            raise


def run(source, database, output, protocol_path=PROTOCOL):
    source, output = outside_checkout(source), outside_checkout(output)
    database = Path(database).resolve()
    require(source.is_file() and database.is_file() and not output.exists())
    protocol_bytes = Path(protocol_path).read_bytes()
    protocol = json.loads(protocol_bytes)
    require(protocol["schema"] == "allelio-public-input-protocol/1"
            and protocol["role"] == "bounded_raw_input_compatibility"
            and protocol["annotation_options"] == OPTIONS)
    original = fingerprints(source)
    require(original["md5"] == protocol["source"]["published_md5"])
    with references(database) as db:
        db_identity = reference_identity(db)
    require(db_identity["logical_sha256"] == protocol["references"]["logical_sha256"])
    software, runner_hash = code_identity(), checksum(__file__)
    output.mkdir(parents=True, mode=0o700)
    output.chmod(0o700)
    (output / "INCOMPLETE").write_text("No final report exists until integrity checks complete.\n")
    (output / "protocol.json").write_bytes(protocol_bytes)
    artifact_hashes = {"protocol.json": hashlib.sha256(protocol_bytes).hexdigest()}
    def retain(document, name):
        write_evidence_export(document, output / name)
        encoded = (json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
        artifact_hashes[name] = hashlib.sha256(encoded).hexdigest()
    started = datetime.now(timezone.utc).isoformat()
    # Raw exceptions/stdout can contain identifying fields. Retain them only locally.
    with private_log(output / "execution.log"), ExitStack() as stack:
        for name in ("socket.socket.connect", "socket.socket.connect_ex", "socket.getaddrinfo", "socket.create_connection"):
            stack.enter_context(patch(name, no_network))
        selection, selected_hash = select_rows(source, output / "selected.vcf", protocol["selection"])
        artifact_hashes["selected.vcf"] = selected_hash
        require(checksum(output / "selected.vcf") == selected_hash)
        retain({"source": original, "selection": selection, "selected_sha256": selected_hash,
            "changed_at": started, "change": protocol["selection"]["transformation"],
            "attribution": "NIST Genome in a Bottle; applicable NIST terms in the retained release README."}, "selection.json")
        manifest, evidence, _ = record_run(output / "selected.vcf", database,
                                          options=protocol["annotation_options"], explain=False)
        retain(manifest, "run.json")
        retain(evidence, "evidence.json")
        errors = validate_evidence(evidence)
        retain({"errors": errors}, "validation-errors.json")
        coverage = evidence["coverage"]
        counts = coverage["counts"]
        require(set(counts) <= STATUSES)
        require(all(type(v) is int and v >= 0 for v in counts.values()))
        parsed = len(evidence["inputs"])
        parser_counts = Counter(row["status"] if row.get("input_id") is None else "parsed" for row in coverage["rows"])
        require(set(parser_counts) <= STATUSES)
        accounted = (coverage["complete"] and coverage["total_rows"] == selection["selected_rows"]
                     == coverage["accounted_rows"] == len(coverage["rows"]) == sum(counts.values())
                     and parser_counts["parsed"] == parsed)
        replay, replayed = replay_run(manifest, output / "selected.vcf", database)
        retain(replay, "replay.json")
        require(replay["annotation_replayed"] and not replay["runtime_differences"]
                and not validate_evidence(replayed))
    require(fingerprints(source) == original and checksum(output / "selected.vcf") == selected_hash
            and manifest["input"]["sha256"] == selected_hash and manifest["references"] == db_identity
            and manifest["software"] == software and code_identity() == software
            and checksum(__file__) == runner_hash and Path(protocol_path).read_bytes() == protocol_bytes
            and (output / "protocol.json").read_bytes() == protocol_bytes
            and annotation_checksum(evidence) == manifest["annotation_sha256"]
            and all(checksum(output / name) == digest for name, digest in artifact_hashes.items()))
    report = {"schema": "allelio-public-input-demonstration/1", "status": "complete",
        "role": protocol["role"], "source_sha256": original["sha256"],
        "source_md5_matches_published": True, "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "runner_sha256": runner_hash, "software": software, "runtime": public_runtime(),
        "references_logical_sha256": db_identity["logical_sha256"],
        "annotation_options": dict(OPTIONS), "selection": selection,
        "processing": {"parsed_rows": parsed, "parser_dispositions": dict(sorted(parser_counts.items())),
            "final_dispositions": dict(sorted(counts.items())), "returned_findings": len(evidence["findings"]),
            "accounting_complete": bool(accounted), "evidence_contract_valid": not errors,
            "evidence_contract_errors": len(errors), "annotation_replayed": True,
            "annotation_accuracy_assessed": False}, "local_artifact_sha256": artifact_hashes,
        "execution_checks_passed": bool(accounted and not errors),
        "limitations": ["One prespecified interval from one public broadly consented research genome; not anonymous.",
            "No identifier/build repair, BED intersection or normalization; complete source rows and headers stay local.",
            "Minimal ClinVar-only references and normal reporting options; no other source or explanation evaluation.",
            "Processing/accounting and replay checks do not establish input support or clinical/variant-call accuracy.",
            "Zero findings are not a negative genetic test. No whole-genome or population performance estimate.",
            "Python network entry points were denied; this is not an operating-system isolation proof."]}
    write_evidence_export(report, output / "report.pending.json")
    (output / "INCOMPLETE").unlink()
    (output / "report.pending.json").replace(output / "report.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        report = run(args.source, args.database, args.output)
    except Exception:
        print("Demonstration incomplete; inspect the local inputs and retained artifacts.", file=sys.stderr)
        return 2
    p = report["processing"]
    print("Selected %d rows; parsed %d; returned %d findings; accounting %s." %
          (report["selection"]["selected_rows"], p["parsed_rows"], p["returned_findings"], p["accounting_complete"]))
    return 0 if report["execution_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
