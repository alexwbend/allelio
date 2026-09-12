"""Validate an evidence JSON document against the shipped schema.

The schema (``allelio/schemas/evidence-<major.minor>.json``, JSON Schema
2020-12) is the structural contract. Two things it cannot say are checked
here as well: that every document-local reference (``input_id``,
``finding_id``, ``candidate_id``) points at something in the same document,
and that the counts which must be conserved (coverage rows, candidate
records, returned findings) add up. Every problem is reported as one line
naming where it is and what was expected, so a consumer can act on it.
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # Python 3.9+: importlib.resources.files
    from importlib.resources import files as _package_files
except ImportError:  # pragma: no cover
    _package_files = None

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_MAJOR = "1"
DEFAULT_SCHEMA_VERSION = "1.0"

_ID_PATTERNS = {
    "input_id": re.compile(r"^input-[1-9][0-9]*$"),
    "finding_id": re.compile(r"^finding-[1-9][0-9]*$"),
    "candidate_id": re.compile(r"^candidate-[1-9][0-9]*$"),
}


def schema_path(version: str = DEFAULT_SCHEMA_VERSION) -> Path:
    """Where the packaged schema for ``version`` lives (works from a wheel)."""
    name = f"evidence-{version}.json"
    if _package_files is not None:
        resource = _package_files("allelio").joinpath("schemas").joinpath(name)
        return Path(str(resource))
    return Path(__file__).parent / "schemas" / name


def load_schema(version: str = DEFAULT_SCHEMA_VERSION) -> Dict[str, Any]:
    """The schema document for ``version``; raises FileNotFoundError if unshipped."""
    return json.loads(schema_path(version).read_text(encoding="utf-8"))


def schema_version_for(document: Dict[str, Any]) -> str:
    """Which shipped schema a document should be checked against.

    Minor versions are additive, so a document at 1.3 validates against the
    newest shipped 1.x schema at or below it; here that is 1.0.
    """
    return DEFAULT_SCHEMA_VERSION


def _structural_errors(document: Any, schema: Dict[str, Any]) -> List[str]:
    """Schema violations as ``path: message`` lines, most general first."""
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - jsonschema is a declared dependency
        return ["jsonschema is not installed; structural validation skipped (pip install jsonschema)"]
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = []
    for error in sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in error.absolute_path) or "(document)"
        errors.append(f"{where}: {error.message}")
    return errors


def _ids(items: Any, key: str) -> List[Any]:
    return [item.get(key) for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def semantic_errors(document: Dict[str, Any]) -> List[str]:
    """Reference and conservation checks JSON Schema alone cannot express.

    Assumes the document is structurally valid enough to walk; anything
    missing is skipped rather than reported twice.
    """
    errors: List[str] = []
    if not isinstance(document, dict):
        return ["(document): expected a JSON object"]

    inputs = document.get("inputs") or []
    findings = document.get("findings") or []
    matching = document.get("matching") or {}
    coverage = document.get("coverage") or {}

    def check_ids(kind: str, values: List[Any], where: str, contiguous: bool) -> set:
        """Ids are document-local: unique, well formed, ascending; contiguous where every one is listed."""
        seen, previous = set(), 0
        pattern = _ID_PATTERNS[kind]
        for index, value in enumerate(values):
            if not isinstance(value, str) or not pattern.match(value):
                errors.append(f"{where}/{index}/{kind}: {value!r} is not a document-local {kind}")
                continue
            number = int(value.split("-")[1])
            if contiguous and number != index + 1:
                errors.append(f"{where}/{index}/{kind}: expected {kind.split('_')[0]}-{index + 1} (sequential), got {value!r}")
            elif number <= previous:
                errors.append(f"{where}/{index}/{kind}: {value!r} is out of order or duplicated")
            if value in seen:
                errors.append(f"{where}/{index}/{kind}: duplicate id {value!r}")
            seen.add(value)
            previous = number
        return seen

    input_ids = check_ids("input_id", _ids(inputs, "input_id"), "inputs", contiguous=True)
    finding_ids = check_ids("finding_id", _ids(findings, "finding_id"), "findings", contiguous=True)
    candidates = matching.get("candidates") or [] if isinstance(matching, dict) else []
    # Candidate ids number every candidate considered, listed or not, so the
    # listed ones are ascending but need not be contiguous.
    candidate_ids = check_ids("candidate_id", _ids(candidates, "candidate_id"), "matching/candidates", contiguous=False)

    def check_refs(values: Any, known: set, kind: str, where: str) -> None:
        if not isinstance(values, list):
            return
        for value in values:
            if value not in known:
                errors.append(f"{where}: {kind} {value!r} does not exist in this document")

    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            continue
        check_refs(finding.get("input_ids"), input_ids, "input_id", f"findings/{index}/input_ids")
        rsids = {inp.get("rsid") for inp in inputs if isinstance(inp, dict) and inp.get("input_id") in set(finding.get("input_ids") or [])}
        if rsids and rsids != {finding.get("rsid")}:
            errors.append(f"findings/{index}/input_ids: referenced inputs carry rsIDs {sorted(rsids)}, finding is {finding.get('rsid')!r}")
        if isinstance(matching, dict) and matching:
            check_refs(finding.get("candidate_ids"), candidate_ids, "candidate_id", f"findings/{index}/candidate_ids")
            for cid in finding.get("candidate_ids") or []:
                candidate = next((c for c in candidates if c.get("candidate_id") == cid), None)
                if candidate and candidate.get("decision") != "retained":
                    errors.append(f"findings/{index}/candidate_ids: {cid} is {candidate.get('decision')!r}, only retained candidates support a finding")
    for index, group in enumerate(document.get("gene_groups") or []):
        if isinstance(group, dict):
            check_refs(group.get("finding_ids"), finding_ids, "finding_id", f"gene_groups/{index}/finding_ids")
            if isinstance(group.get("indices"), list) and any(
                not isinstance(i, int) or i < 0 or i >= len(findings) for i in group["indices"]
            ):
                errors.append(f"gene_groups/{index}/indices: index outside findings")
            if isinstance(group.get("count"), int) and isinstance(group.get("finding_ids"), list) \
                    and group["count"] != len(set(group["finding_ids"])):
                errors.append(f"gene_groups/{index}/count: {group['count']} but {len(set(group['finding_ids']))} distinct finding_ids")

    # Coverage: rows are conserved and the finding count is the findings array.
    if isinstance(coverage, dict) and coverage:
        rows = coverage.get("rows") or []
        counts = coverage.get("counts") or {}
        if isinstance(rows, list) and coverage.get("accounted_rows") != len(rows):
            errors.append(f"coverage/accounted_rows: {coverage.get('accounted_rows')} but {len(rows)} rows listed")
        if isinstance(counts, dict) and isinstance(rows, list):
            observed = dict(Counter(r.get("status") for r in rows if isinstance(r, dict)))
            if {k: v for k, v in counts.items()} != observed:
                errors.append(f"coverage/counts: {counts} does not match the listed rows {observed}")
        if isinstance(coverage.get("accounted_rows"), int) and isinstance(coverage.get("total_rows"), int) \
                and coverage["accounted_rows"] > coverage["total_rows"]:
            errors.append("coverage/accounted_rows: exceeds total_rows")
        if coverage.get("returned_findings") != len(findings):
            errors.append(f"coverage/returned_findings: {coverage.get('returned_findings')} but {len(findings)} findings")
        complete = coverage.get("accounted_rows") == coverage.get("total_rows") and not (counts or {}).get("unaccounted")
        if isinstance(coverage.get("complete"), bool) and coverage["complete"] != complete:
            errors.append(f"coverage/complete: {coverage['complete']} but rows say {complete}")
        for index, row in enumerate(rows if isinstance(rows, list) else []):
            if isinstance(row, dict) and row.get("input_id") is not None and row["input_id"] not in input_ids:
                errors.append(f"coverage/rows/{index}/input_id: {row['input_id']!r} does not exist in this document")

    # Matching: candidate counts are conserved and sites reference what they list.
    if isinstance(matching, dict) and matching:
        counts = matching.get("counts") or {}
        total = matching.get("candidate_count")
        if isinstance(counts, dict) and sum(counts.values()) != total:
            errors.append(f"matching/counts: sum {sum(counts.values())} but candidate_count {total}")
        by_source = matching.get("by_source") or {}
        if isinstance(by_source, dict) and sum(sum(v.values()) for v in by_source.values() if isinstance(v, dict)) != total:
            errors.append("matching/by_source: does not sum to candidate_count")
        if matching.get("listed_candidate_count") != len(candidates):
            errors.append(f"matching/listed_candidate_count: {matching.get('listed_candidate_count')} but {len(candidates)} candidates listed")
        sites = matching.get("sites") or []
        if isinstance(sites, list):
            if matching.get("sites_with_candidates") != len(sites):
                errors.append(f"matching/sites_with_candidates: {matching.get('sites_with_candidates')} but {len(sites)} sites")
            if sum(s.get("candidate_count", 0) for s in sites if isinstance(s, dict)) != total:
                errors.append("matching/sites: candidate_count over sites does not sum to matching/candidate_count")
            listed = 0
            for index, site in enumerate(sites):
                if not isinstance(site, dict):
                    continue
                check_refs(site.get("input_ids"), input_ids, "input_id", f"matching/sites/{index}/input_ids")
                if site.get("finding_id") is not None and site["finding_id"] not in finding_ids:
                    errors.append(f"matching/sites/{index}/finding_id: {site['finding_id']!r} does not exist in this document")
                ids = site.get("candidate_ids")
                if site.get("candidates_listed"):
                    if not isinstance(ids, list):
                        errors.append(f"matching/sites/{index}/candidate_ids: listed site must enumerate its candidates")
                    else:
                        listed += len(ids)
                        check_refs(ids, candidate_ids, "candidate_id", f"matching/sites/{index}/candidate_ids")
                        if len(ids) != site.get("candidate_count"):
                            errors.append(f"matching/sites/{index}/candidate_count: {site.get('candidate_count')} but {len(ids)} candidate_ids")
                elif ids is not None:
                    errors.append(f"matching/sites/{index}/candidate_ids: must be null when candidates are not listed")
            if listed != len(candidates):
                errors.append(f"matching/sites: listed candidate_ids total {listed} but {len(candidates)} candidates")
        for index, candidate in enumerate(candidates):
            if isinstance(candidate, dict) and candidate.get("finding_id") is not None:
                if candidate["finding_id"] not in finding_ids:
                    errors.append(f"matching/candidates/{index}/finding_id: {candidate['finding_id']!r} does not exist in this document")
                elif candidate.get("decision") != "retained":
                    errors.append(f"matching/candidates/{index}/finding_id: a {candidate.get('decision')!r} candidate cannot support a finding")
    # Cross-check relationships, not just existence and aggregate totals.
    if isinstance(matching, dict) and matching:
        candidate_map = {c["candidate_id"]: c for c in candidates}
        finding_map = {f["finding_id"]: f for f in findings}
        input_map = {i["input_id"]: i for i in inputs}
        assigned = []
        site_totals = Counter()
        for index, site in enumerate(matching.get("sites") or []):
            counts = site.get("counts") or {}
            site_totals.update(counts)
            if sum(counts.values()) != site["candidate_count"]:
                errors.append(f"matching/sites/{index}/counts: does not sum to candidate_count")
            for iid in site.get("input_ids") or []:
                if iid in input_map and input_map[iid]["rsid"] != site["rsid"]:
                    errors.append(f"matching/sites/{index}/input_ids: input belongs to a different rsID")
            fid = site.get("finding_id")
            if fid in finding_map and finding_map[fid]["rsid"] != site["rsid"]:
                errors.append(f"matching/sites/{index}/finding_id: finding belongs to a different rsID")
            ids = site.get("candidate_ids") or []
            assigned.extend(ids)
            listed_records = [candidate_map[cid] for cid in ids if cid in candidate_map]
            if site.get("candidates_listed") and Counter(c["decision"] for c in listed_records) != Counter(counts):
                errors.append(f"matching/sites/{index}/counts: does not match listed candidate decisions")
            for candidate in listed_records:
                if candidate["rsid"] != site["rsid"]:
                    errors.append(f"matching/sites/{index}/candidate_ids: candidate belongs to a different rsID")
        if Counter(assigned) != Counter(candidate_map.keys()):
            errors.append("matching/sites: each listed candidate must belong to exactly one site")
        if site_totals != Counter(matching.get("counts") or {}):
            errors.append("matching/counts: does not match site decision totals")
        source_totals = Counter()
        for counts in (matching.get("by_source") or {}).values():
            source_totals.update(counts)
        if source_totals != Counter(matching.get("counts") or {}):
            errors.append("matching/by_source: decision totals do not match matching/counts")
        for index, candidate in enumerate(candidates):
            fid = candidate.get("finding_id")
            if fid in finding_map:
                finding = finding_map[fid]
                if finding["rsid"] != candidate["rsid"] or candidate["candidate_id"] not in (finding.get("candidate_ids") or []):
                    errors.append(f"matching/candidates/{index}/finding_id: support must be reciprocal and share the rsID")
        for index, finding in enumerate(findings):
            for cid in finding.get("candidate_ids") or []:
                candidate = candidate_map.get(cid)
                if candidate and candidate.get("finding_id") != finding["finding_id"]:
                    errors.append(f"findings/{index}/candidate_ids: candidate does not link back to this finding")
    return errors


def validate_evidence(document: Any, schema: Optional[Dict[str, Any]] = None) -> List[str]:
    """All problems with ``document``: structural first, then semantic.

    Returns an empty list for a valid document. Each line names the JSON
    location and what was expected.
    """
    if not isinstance(document, dict):
        return ["(document): expected a JSON object"]
    declared = str(document.get("schema_version", ""))
    if declared.split(".")[0] != SCHEMA_MAJOR:
        return [f"schema_version: {declared!r} is not a {SCHEMA_MAJOR}.x document; this validator ships schema {DEFAULT_SCHEMA_VERSION}"]
    schema = schema or load_schema(schema_version_for(document))
    errors = _structural_errors(document, schema)
    # Semantic checks require structurally typed containers and references.
    if not errors:
        errors.extend(semantic_errors(document))
    return errors


def validate_evidence_file(path: str) -> List[str]:
    """Validate the JSON file at ``path``; a parse failure is one error line."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{path}: not readable as JSON ({exc})"]
    return validate_evidence(document)
