"""Freeze source-derived internal cases without consulting Allelio's annotator.

This selector intentionally reads the source TSV directly, independently of the
production ClinVar parser. Constructed genotypes are not participant observations.
"""
import csv
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


SCENARIOS = ("reference", "heterozygous", "alternate", "unknown_build",
             "wrong_build", "wrong_position", "wrong_allele", "failed_filter", "no_call")
REQUIRED = {"#AlleleID", "Type", "GeneSymbol", "HGNC_ID", "ClinicalSignificance",
            "RS# (dbSNP)", "Assembly", "Chromosome", "ReviewStatus", "VariationID",
            "PositionVCF", "ReferenceAlleleVCF", "AlternateAlleleVCF",
            "SomaticClinicalImpact", "ReviewStatusClinicalImpact", "Oncogenicity",
            "ReviewStatusOncogenicity"}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rows(path):
    opener = gzip.open if Path(path).suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = reader.fieldnames or []
        if len(header) != len(set(header)) or not REQUIRED.issubset(header):
            raise ValueError("A unique, named post-split ClinVar header is required.")
        for number, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Malformed ClinVar row at line %d." % number)
            yield row


def positive_integer(value):
    return bool(re.fullmatch(r"[1-9][0-9]{0,18}", value or "")) and int(value) < 2**63


def candidate(row, selection):
    """Return the first exclusion reason, or the minimal source record."""
    rules = ((row["Assembly"] == selection["assembly"], "assembly"),
             (row[selection["review_field"]] in selection["review_statuses"], "germline_review_status"),
             (row["Chromosome"] in selection["chromosomes"], "chromosome"),
             (row["Type"] == selection["variant_type"], "variant_type"),
             (row[selection["classification_field"]] in selection["classifications"], "germline_classification"))
    for allowed, reason in rules:
        if not allowed:
            return reason
    if not all(positive_integer(row[key]) for key in
               ("#AlleleID", "VariationID", "RS# (dbSNP)", "PositionVCF")):
        return "identity_missing_or_invalid"
    ref, alt = row["ReferenceAlleleVCF"], row["AlternateAlleleVCF"]
    if ref not in "ACGT" or alt not in "ACGT" or len(ref) != 1 or len(alt) != 1 or ref == alt:
        return "unsupported_alleles"
    return {"rsid": "rs" + row["RS# (dbSNP)"], "allele_id": row["#AlleleID"],
            "variation_id": row["VariationID"], "assembly": row["Assembly"],
            "chromosome": row["Chromosome"], "position": int(row["PositionVCF"]),
            "ref": ref, "alt": alt, "gene": row["GeneSymbol"], "hgnc_id": row["HGNC_ID"],
            "germline_classification": row["ClinicalSignificance"],
            "germline_review_status": row["ReviewStatus"]}


def cases(record):
    """Rule-derived expectations over deliberately constructed VCF records.

    Counts describe the selected source ALT, not disease or pathogenicity truth.
    Unknown identity never receives an invented source-allele copy count.
    """
    for scenario in SCENARIOS:
        copies = {"reference": 0, "alternate": 2}.get(scenario, 1)
        value = {"reference_declaration": "GRCh38", "chromosome": record["chromosome"],
                 "position": record["position"], "rsid": record["rsid"],
                 "ref": record["ref"], "alt": record["alt"], "filter": "PASS",
                 "gt": {0: "0/0", 1: "0/1", 2: "1/1"}[copies]}
        expected = {"parsed": True, "filter_excluded": False,
                    "source_allele_match": "absent" if copies == 0 else "carried",
                    "source_alt_copies": copies}
        if scenario in ("unknown_build", "wrong_build", "wrong_position", "wrong_allele"):
            expected.update(source_allele_match="unknown", source_alt_copies=None)
            if scenario == "unknown_build":
                value["reference_declaration"] = None
            elif scenario == "wrong_build":
                value["reference_declaration"] = "GRCh37"
            elif scenario == "wrong_position":
                value["position"] += 1
            else:
                value["alt"] = next(base for base in "ACGT" if base not in (record["ref"], record["alt"]))
        elif scenario in ("failed_filter", "no_call"):
            expected.update(source_allele_match="not_evaluated", source_alt_copies=None)
            if scenario == "failed_filter":
                value["filter"] = "q10"
                expected["filter_excluded"] = True
            else:
                value["gt"] = "./."
                expected["parsed"] = False
        yield {"id": record["rsid"] + "-" + scenario, "record_rsid": record["rsid"],
               "scenario": scenario, "input": value, "expected": expected}


def build_reference_set(source, protocol_path, output):
    source, protocol_path, output = Path(source), Path(protocol_path), Path(output)
    protocol_bytes = protocol_path.read_bytes()
    protocol = json.loads(protocol_bytes)
    if protocol.get("schema") != "allelio-clinvar-reference-protocol/1":
        raise ValueError("Unsupported reference-set protocol.")
    selection = protocol["selection"]
    if (selection["assembly"] != "GRCh38" or selection["review_field"] != "ReviewStatus"
            or selection["classification_field"] != "ClinicalSignificance"
            or selection["require_unique_grch38_rsid"] is not True
            or protocol["case_scenarios"] != list(SCENARIOS)):
        raise ValueError("Unsupported selection or scenario contract.")
    if output.exists():
        raise ValueError("Use a new output directory; frozen sets are never overwritten.")
    if sha256(source) != protocol["source"]["sha256"]:
        raise ValueError("Source checksum does not match the frozen protocol.")
    exclusions, candidates = Counter(), {}
    total = eligible_rows = 0
    for row in rows(source):
        total += 1
        item = candidate(row, selection)
        if isinstance(item, str):
            exclusions[item] += 1
        else:
            eligible_rows += 1
            candidates[item["rsid"]] = item
    # Check *all* GRCh38 rows for a candidate rsID, not only high-review rows:
    # another allele or lower-review assertion must not be silently hidden.
    occurrences = Counter()
    for row in rows(source):
        rsid = "rs" + row["RS# (dbSNP)"]
        if row["Assembly"] == "GRCh38" and rsid in candidates:
            occurrences[rsid] += 1
    selected = sorted((record for rsid, record in candidates.items() if occurrences[rsid] == 1),
                      key=lambda record: (int(record["chromosome"]), record["position"], int(record["allele_id"])))
    # A second checksum detects ordinary concurrent source replacement.
    if sha256(source) != protocol["source"]["sha256"]:
        raise ValueError("Source changed while selecting the reference set.")
    if not selected:
        raise ValueError("No eligible unambiguous source records.")
    output.mkdir(parents=True)
    (output / "protocol.json").write_bytes(protocol_bytes)
    with (output / "records.jsonl").open("w", encoding="utf-8", newline="\n") as records_file, \
            (output / "cases.jsonl").open("w", encoding="utf-8", newline="\n") as cases_file:
        for record in selected:
            records_file.write(json.dumps(record, sort_keys=True) + "\n")
            for case in cases(record):
                cases_file.write(json.dumps(case, sort_keys=True) + "\n")
    manifest = {"schema": "allelio-clinvar-reference-set/1", "protocol_version": protocol["version"],
                "evidence_type": "internal_source_fidelity", "independent_validation": False,
                "genotypes": "constructed; not participant observations", "source": protocol["source"],
                "builder_sha256": sha256(__file__),
                "artifacts": {name: sha256(output / name) for name in ("protocol.json", "records.jsonl", "cases.jsonl")},
                "selection_counts": {"source_rows": total, "first_rule_exclusions": dict(sorted(exclusions.items())),
                                     "eligible_source_rows": eligible_rows,
                                     "ambiguous_eligible_rows": eligible_rows - len(selected),
                                     "candidate_rsids": len(candidates), "ambiguous_rsids": sum(n > 1 for n in occurrences.values()),
                                     "selected_records": len(selected)},
                "strata": {key: dict(sorted(Counter(r[key] for r in selected).items())) for key in
                           ("germline_classification", "germline_review_status", "chromosome")},
                "case_counts": {"total": len(selected) * len(SCENARIOS),
                                "by_scenario": {scenario: len(selected) for scenario in SCENARIOS}},
                "limitations": ["Source-derived expectations are not independent clinical truth.",
                                "Selected unambiguous GRCh38 autosomal SNVs are not representative of all variants.",
                                "No Allelio outcomes have been measured by building this set.",
                                "Case/reference records are local artifacts; publication requires separate review."],
                "rights_review": protocol["rights_review"]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
