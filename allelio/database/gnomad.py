"""gnomAD population frequency database parser.

Parses the compact frequency extract ``scripts/build_gnomad_freq.py`` writes
and yields records ready for batch insertion into SQLite.

Two layouts exist. Format 1 (the extract published for 0.3.0) keys rows by
rsID alone and carries no allele: at a multiallelic site it silently kept the
first alternate allele's frequency, and nothing in it says which build or
position it describes. Format 2 adds chromosome, position, REF and ALT per
row, one row per alternate allele, and declares the assembly and source
release in its ``##`` header. Records from a format 1 file keep empty allele
fields so they can be shown as unverified context, never as the matched
allele's frequency.
"""

import gzip
import re
from typing import Generator, Dict, Any, Optional
from pathlib import Path


# Expected TSV column headers (flexible — we detect by header line)
GNOMAD_TSV_COLUMNS = {
    "rsid": None,
    "allele_frequency": None,
    "af_popmax": None,
    "ac": None,
    "an": None,
    "nhomalt": None,
    "af_afr": None,
    "af_eas": None,
    "af_fin": None,
    "af_nfe": None,
    "af_sas": None,
}

# Mapping of common gnomAD header variations to our field names
HEADER_ALIASES = {
    "rsid": ["rsid", "rs_id", "rsID", "snp", "SNP", "variant_id"],
    "chromosome": ["chrom", "chromosome", "chr", "CHROM"],
    "position": ["pos", "position", "POS"],
    "ref_allele": ["ref", "ref_allele", "REF", "reference_allele"],
    "alt_allele": ["alt", "alt_allele", "ALT", "alternate_allele"],
    "allele_frequency": ["allele_frequency", "AF", "af", "freq", "frequency", "global_af"],
    "af_popmax": ["af_popmax", "AF_popmax", "popmax_af", "AF_POPMAX",
                  "af_grpmax", "AF_grpmax", "grpmax_af", "AF_GRPMAX"],
    "ac": ["ac", "AC", "allele_count"],
    "an": ["an", "AN", "allele_number"],
    "nhomalt": ["nhomalt", "nhomalt", "n_homozygotes", "hom_count"],
    "af_afr": ["af_afr", "AF_afr", "AF_AFR"],
    "af_eas": ["af_eas", "AF_eas", "AF_EAS"],
    "af_fin": ["af_fin", "AF_fin", "AF_FIN"],
    "af_nfe": ["af_nfe", "AF_nfe", "AF_NFE"],
    "af_sas": ["af_sas", "AF_sas", "AF_SAS"],
}


def _safe_float(value: str) -> Optional[float]:
    """Convert string to float, returning None for invalid or missing values."""
    if not value or value in ("-", ".", "NA", "nan", "None", ""):
        return None
    try:
        f = float(value)
        if f < 0 or f > 1.0:
            return None
        return f
    except (ValueError, TypeError):
        return None


def _safe_int(value: str) -> Optional[int]:
    """Convert string to int, returning None for invalid or missing values."""
    if not value or value in ("-", ".", "NA", "nan", "None", ""):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


# Header lines the build script writes; the values travel into every record
# and into the database metadata so a report can say which assembly and
# release a frequency came from.
_HEADER_KEYS = {
    "format": re.compile(r"^##\s*Format:\s*(\d+)", re.I),
    "assembly": re.compile(r"^##\s*Assembly:\s*(\S+)", re.I),
    "source_version": re.compile(r"^##\s*Source:\s*gnomAD\s*(v?[\d.]+)", re.I),
}


def _open(filepath: str):
    is_gzipped = filepath.endswith(".gz") or filepath.endswith(".bgz")
    return (gzip.open if is_gzipped else open)(Path(filepath), "rt" if is_gzipped else "r", encoding="utf-8")


def gnomad_file_header(filepath: str) -> Dict[str, Optional[str]]:
    """What the ``##`` preamble declares: format, assembly, source_version.

    A format 1 file declares no assembly; the keys are then None, and the
    format reads "1". Reading stops at the first non-comment line.
    """
    found: Dict[str, Optional[str]] = {key: None for key in _HEADER_KEYS}
    with _open(filepath) as f:
        for line in f:
            if not line.startswith("##"):
                break
            for key, pattern in _HEADER_KEYS.items():
                m = pattern.match(line)
                if m and found[key] is None:
                    found[key] = m.group(1)
    found["format"] = found["format"] or "1"
    return found


def _text(fields, index: Optional[int]) -> str:
    """A column as text, '' when absent or a placeholder."""
    if index is None or index >= len(fields):
        return ""
    value = fields[index].strip()
    return "" if value in ("-", ".", "NA") else value


def _detect_column_indices(header_fields: list) -> Dict[str, Optional[int]]:
    """Map header fields to our expected column names using aliases.

    Args:
        header_fields: List of column header strings from the TSV

    Returns:
        Dict mapping our field names to column indices (None if not found)
    """
    indices = {}
    header_lower = [h.strip().lower() for h in header_fields]

    for field_name, aliases in HEADER_ALIASES.items():
        indices[field_name] = None
        for alias in aliases:
            if alias.lower() in header_lower:
                indices[field_name] = header_lower.index(alias.lower())
                break

    return indices


def parse_gnomad(filepath: str) -> Generator[Dict[str, Any], None, None]:
    """Parse gnomAD allele frequency data from a TSV file.

    Supports both plain and gzipped (.gz) TSV files. Detects column
    layout from the header row. Skips lines without valid rsIDs.

    Args:
        filepath: Path to gnomAD TSV file (.tsv or .tsv.gz)

    Yields:
        Dict with keys matching the gnomad database table schema:
        rsid, chromosome, position, ref_allele, alt_allele, assembly,
        source_version, allele_frequency, af_popmax, ac, an, nhomalt,
        af_afr, af_eas, af_fin, af_nfe, af_sas. Identity fields are ''/None
        for a format 1 file.
    """
    header = gnomad_file_header(filepath)
    assembly, source_version = header["assembly"], header["source_version"]
    column_indices = None

    with _open(filepath) as f:
        for line_num, line in enumerate(f, 1):
            line = line.rstrip("\n")

            # Skip comment lines
            if line.startswith("##"):
                continue

            fields = line.split("\t")

            # Detect header row and build column index map
            if column_indices is None:
                # Check if this looks like a header line
                if any(alias.lower() in line.lower() for alias in ["rsid", "rs_id", "snp", "AF"]):
                    column_indices = _detect_column_indices(fields)
                    # Verify we found at least rsid and allele_frequency
                    if column_indices.get("rsid") is None:
                        raise ValueError(
                            f"gnomAD file header missing rsID column. "
                            f"Found headers: {fields[:10]}"
                        )
                    continue
                else:
                    # No header detected — assume standard column order
                    column_indices = {
                        "rsid": 0,
                        "chromosome": None,
                        "position": None,
                        "ref_allele": None,
                        "alt_allele": None,
                        "allele_frequency": 1,
                        "af_popmax": 2,
                        "ac": 3,
                        "an": 4,
                        "nhomalt": 5,
                        "af_afr": 6,
                        "af_eas": 7,
                        "af_fin": 8,
                        "af_nfe": 9,
                        "af_sas": 10,
                    }

            try:
                # Extract rsID
                rsid_idx = column_indices.get("rsid")
                if rsid_idx is None or rsid_idx >= len(fields):
                    continue

                rsid = fields[rsid_idx].strip()

                # Must have a valid rsID
                if not rsid or rsid in ("-", "."):
                    continue
                if not rsid.startswith("rs"):
                    continue

                # Extract allele frequency
                af_idx = column_indices.get("allele_frequency")
                af_value = None
                if af_idx is not None and af_idx < len(fields):
                    af_value = _safe_float(fields[af_idx])

                # Build record
                record = {
                    "rsid": rsid,
                    "chromosome": _text(fields, column_indices.get("chromosome")),
                    "position": _safe_int(_text(fields, column_indices.get("position"))),
                    "ref_allele": _text(fields, column_indices.get("ref_allele")).upper(),
                    "alt_allele": _text(fields, column_indices.get("alt_allele")).upper(),
                    "assembly": assembly,
                    "source_version": source_version,
                    "allele_frequency": af_value,
                }
                if record["chromosome"].startswith("chr"):
                    record["chromosome"] = record["chromosome"][3:]

                # Extract optional fields
                for field_name in ["af_popmax", "af_afr", "af_eas", "af_fin", "af_nfe", "af_sas"]:
                    idx = column_indices.get(field_name)
                    if idx is not None and idx < len(fields):
                        record[field_name] = _safe_float(fields[idx])
                    else:
                        record[field_name] = None

                for field_name in ["ac", "an", "nhomalt"]:
                    idx = column_indices.get(field_name)
                    if idx is not None and idx < len(fields):
                        record[field_name] = _safe_int(fields[idx])
                    else:
                        record[field_name] = None

                yield record

            except (IndexError, ValueError):
                # Skip malformed lines
                continue
