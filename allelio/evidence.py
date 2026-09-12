"""Versioned, local structured evidence exports (no AI interpretation)."""

import json
import math
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

from collections import Counter

from allelio import __version__
from allelio.coverage import build_coverage
from allelio.analysis.genes import group_findings
from allelio.analysis.trace import PATHS, RETAINED

SCHEMA_VERSION = "1.0"

# Site dispositions whose candidates are exported only on request: a site
# where the person carries none of the annotated alleles has its records
# rejected as "allele_absent", and on a whole-array file there are tens of
# thousands of them. Their counts are always in the document.
DETAILED_ONLY_DISPOSITIONS = {"reference_or_no_applicable_annotation"}


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


def build_matching_trace(stats, finding_ids_by_rsid, input_ids_by_rsid, detailed=False):
    """The candidate-level matching trace as a JSON-ready section.

    Every candidate decision gets a document-local ``candidate_id``; sites
    link their candidates to the finding (if any) and the input rows for
    the rsID. Counts are over candidate records, not input rows or findings.
    Unless ``detailed``, candidates at sites set aside as reference genotype
    are counted but not listed (see DETAILED_ONLY_DISPOSITIONS).
    """
    trace = getattr(stats, "trace", None)
    candidates = list(getattr(trace, "candidates", []) or [])
    dispositions = getattr(stats, "dispositions", {}) or {}
    by_site = {}
    for index, candidate in enumerate(candidates):
        candidate.candidate_id = "candidate-" + str(index + 1)
        by_site.setdefault(candidate.rsid, []).append(candidate)
    sites, listed = [], []
    for rsid, site_candidates in by_site.items():
        disposition = dispositions.get(rsid)
        include = detailed or disposition not in DETAILED_ONLY_DISPOSITIONS
        counts = dict(sorted(Counter(c.decision for c in site_candidates).items()))
        sites.append({
            "rsid": rsid,
            "input_ids": input_ids_by_rsid.get(rsid, []),
            "finding_id": finding_ids_by_rsid.get(rsid),
            "disposition": disposition,
            "candidate_count": len(site_candidates),
            "counts": counts,
            "candidate_ids": [c.candidate_id for c in site_candidates] if include else None,
            "candidates_listed": include,
        })
        if include:
            listed.extend(site_candidates)
    by_source = {}
    for candidate in candidates:
        by_source.setdefault(candidate.source, Counter())[candidate.decision] += 1
    return {
        "schema": "candidate-trace/1",
        "candidate_count": len(candidates),
        "counts": dict(sorted(Counter(c.decision for c in candidates).items())),
        "by_source": {source: dict(sorted(counts.items())) for source, counts in sorted(by_source.items())},
        "sites_with_candidates": len(sites),
        "listed_candidate_count": len(listed),
        "detailed": bool(detailed),
        "paths": dict(PATHS),
        "sites": sites,
        "candidates": [
            {
                "candidate_id": c.candidate_id, "rsid": c.rsid, "source": c.source,
                "identity": dict(c.identity), "decision": c.decision, "stage": c.stage,
                "reason": c.reason, "note": c.note,
                "finding_id": finding_ids_by_rsid.get(c.rsid) if c.decision == RETAINED else None,
            }
            for c in listed
        ],
        "limitations": [
            "Candidate counts are over reference records considered, not input rows (see coverage) or findings.",
            "A retained candidate at a site without a finding was set aside by a later rule; the site disposition says which.",
            "Candidate IDs are local to this document and carry no genomic identity of their own; the identity field is what the source gave.",
            "Traces record Allelio's matching decisions only; no AI-generated reasoning is included.",
            "Candidates at reference-genotype sites are counted but listed only in a detailed export.",
        ],
    }


def build_evidence_export(results, inputs, provenance, configuration=None, stats=None, detailed_trace=False):
    """Preserve parsed observations and every source field retained in findings.

    IDs are document-local indices, not normalized genomic identifiers.
    Source records are the selected database annotations, not a raw database dump.
    AI text is deliberately separate from this reproducible evidence contract.
    ``detailed_trace`` lists every candidate record, including those at
    reference-genotype sites; otherwise those are counted only.
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
    finding_ids_by_rsid = {}
    for index, result in enumerate(results):
        record = _json_value(result)
        record["finding_id"] = "finding-" + str(index + 1)
        record["input_ids"] = by_rsid.get(result.rsid, [])
        finding_ids_by_rsid.setdefault(result.rsid, record["finding_id"])
        findings.append(record)
    matching = build_matching_trace(stats, finding_ids_by_rsid, by_rsid, detailed=detailed_trace)
    supporting = {}
    for candidate in matching["candidates"]:
        if candidate["decision"] == RETAINED and candidate["finding_id"]:
            supporting.setdefault(candidate["finding_id"], []).append(candidate["candidate_id"])
    for record in findings:
        record["candidate_ids"] = supporting.get(record["finding_id"], [])
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
        "analysis_stats": _stats_without_trace(stats),
        "coverage": build_coverage(inputs, results, stats),
        "matching": matching,
        "limitations": [
            "Research and education only; not a clinical interpretation.",
            "Document-local IDs do not assert normalized genomic identity.",
            "Source records are annotations retained by matching, not all database candidates.",
            "Missing and non-finite numeric values are null, not zero.",
            "Coverage records parsing exclusions when an input audit is available; absent findings are not negative results.",
            "The matching section records why each candidate source record was retained, rejected, or left unresolved; its counts are over records, not rows or findings.",
        ],
    })


def _stats_without_trace(stats):
    """``analysis_stats`` as before; the trace is exported as ``matching``."""
    if stats is None:
        return None
    record = _json_value(stats)
    if isinstance(record, dict):
        record.pop("trace", None)
    return record


def write_evidence_export(document, path):
    """Write strict JSON; callers must surface write errors."""
    serialized = json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(serialized + "\n", encoding="utf-8")
