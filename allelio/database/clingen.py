"""ClinGen gene-disease validity parser.

ClinGen curates which gene-disease relationships are established and how
each is inherited (its MOI column: AD, AR, XL, SD, MT, UD). Allelio uses the
mode of inheritance to tell a carrier from an affected genotype, and shows
the validity classification as a confidence indicator. The download is one
CSV of a few thousand rows, released under CC0 1.0; ClinGen asks to be
credited with the access date, which the report does.

Format: a few preamble lines ("CLINGEN GENE DISEASE VALIDITY CURATIONS",
"FILE CREATED: YYYY-MM-DD", ...), a "+++" rule, the header row, another
rule, then data.
"""

import csv
import re
from pathlib import Path
from typing import Any, Dict, Generator, Optional

CLINGEN_COLUMNS = {
    "gene": "GENE SYMBOL",
    "hgnc_id": "GENE ID (HGNC)",
    "disease": "DISEASE LABEL",
    "mondo_id": "DISEASE ID (MONDO)",
    "moi": "MOI",
    "classification": "CLASSIFICATION",
    "report_url": "ONLINE REPORT",
    "classification_date": "CLASSIFICATION DATE",
}

# How ClinGen abbreviates modes of inheritance.
MOI_LABELS = {
    "AD": "autosomal dominant",
    "AR": "autosomal recessive",
    "XL": "X-linked",
    "SD": "semidominant",
    "MT": "mitochondrial",
    "UD": "undetermined",
}

_CREATED_RE = re.compile(r"FILE CREATED:\s*(\d{4}-\d{2}-\d{2})")


def clingen_release_date(filepath: str) -> Optional[str]:
    """The ``FILE CREATED`` date from the preamble, as YYYY-MM-DD, or None."""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for _ in range(10):
            m = _CREATED_RE.search(f.readline())
            if m:
                return m.group(1)
    return None


def parse_clingen(filepath: str) -> Generator[Dict[str, Any], None, None]:
    """Yield one dict per gene-disease validity curation.

    Keys: gene, hgnc_id, disease, mondo_id, moi, classification, report_url,
    classification_date. Rows before the header, and the "+++" rules, are
    skipped; rows without a gene symbol are skipped.
    """
    with open(Path(filepath), "r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.reader(f)
        indices = None
        for row in reader:
            if not row:
                continue
            if indices is None:
                if row[0].strip() == CLINGEN_COLUMNS["gene"]:
                    indices = {}
                    for key, name in CLINGEN_COLUMNS.items():
                        try:
                            indices[key] = row.index(name)
                        except ValueError:
                            indices[key] = None
                continue
            if row[0].startswith("+++"):
                continue
            gene = row[indices["gene"]].strip() if indices["gene"] is not None else ""
            if not gene:
                continue

            def field(key):
                i = indices.get(key)
                return row[i].strip() if i is not None and i < len(row) else None

            yield {
                "gene": gene,
                "hgnc_id": field("hgnc_id") or None,
                "disease": field("disease") or None,
                "mondo_id": field("mondo_id") or None,
                "moi": (field("moi") or "").upper() or None,
                "classification": field("classification") or None,
                "report_url": field("report_url") or None,
                "classification_date": (field("classification_date") or "")[:10] or None,
            }
