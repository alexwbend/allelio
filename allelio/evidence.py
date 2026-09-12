"""Versioned, local structured evidence exports (no AI interpretation)."""

import json
import math
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

from allelio import __version__
from allelio.analysis.genes import group_findings

SCHEMA_VERSION = "1.0"


def _json_value(value):
    """Represent unavailable/non-finite source numbers as JSON null."""
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def build_evidence_export(results, inputs, provenance, configuration=None, stats=None):
    """Preserve parsed observations and every source field retained in findings.

    IDs are document-local indices, not normalized genomic identifiers.
    Source records are the selected database annotations, not a raw database dump.
    AI text is deliberately separate from this reproducible evidence contract.
    """
    observations = []
    by_rsid = {}
    for index, variant in enumerate(inputs):
        record = _json_value(variant)
        if not isinstance(record, dict):
            record = {"rsid": str(variant)}
        record["input_id"] = "input-" + str(index + 1)
        observations.append(record)
        by_rsid.setdefault(record.get("rsid"), []).append(record["input_id"])
    findings = []
    for index, result in enumerate(results):
        record = _json_value(result)
        record["finding_id"] = "finding-" + str(index + 1)
        record["input_ids"] = by_rsid.get(result.rsid, [])
        findings.append(record)
    groups = group_findings(results)
    for group in groups:
        group["finding_ids"] = [findings[i]["finding_id"] for i in group["indices"]]
    return _json_value({
        "schema_version": SCHEMA_VERSION,
        "software": {"name": "Allelio", "version": __version__},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configuration": configuration or {},
        "provenance": provenance,
        "inputs": observations,
        "findings": findings,
        "gene_groups": groups,
        "analysis_stats": stats,
        "limitations": [
            "Research and education only; not a clinical interpretation.",
            "Document-local IDs do not assert normalized genomic identity.",
            "Source records are annotations retained by matching, not all database candidates.",
            "Missing and non-finite numeric values are null, not zero.",
            "Parsed inputs omit rows rejected by parsing; absent findings are not negative results.",
        ],
    })


def write_evidence_export(document, path):
    """Write strict JSON; callers must surface write errors."""
    serialized = json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(serialized + "\n", encoding="utf-8")
