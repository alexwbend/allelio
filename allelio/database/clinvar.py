"""ClinVar reference database parser.

Reads ``variant_summary.txt.gz``, ClinVar's per-allele, per-assembly summary.
Every column that carries context a reader needs to interpret an assertion
is kept as the source writes it; see docs/clinvar-fields.md for the mapping.

Two things about this file decide how it is read:

* Since the 2024 classification split, ``ClinicalSignificance`` is the
  aggregate *germline* classification, and somatic clinical impact and
  oncogenicity have their own columns, review statuses and dates. Files
  from before the split mixed them in one column, so a record says which
  kind it holds (``classification_type``) instead of assuming.
* It is aggregated per allele: the classification is the aggregate across
  every condition in PhenotypeList, and the per-condition (RCV) assertions
  are listed by accession only. They are kept as accessions; their
  individual classifications are not in this file and are not invented.
"""

import gzip
from typing import Generator, Dict, Any, Optional
from pathlib import Path


# ClinVar variant_summary.txt column indices, as documented by NCBI. The
# header row is read too, and a column found by name wins over its index,
# so a file with columns added or reordered still maps correctly.
CLINVAR_COLUMNS = {
    "#AlleleID": 0,
    "Type": 1,
    "Name": 2,
    "GeneID": 3,
    "GeneSymbol": 4,
    "HGNC_ID": 5,
    "ClinicalSignificance": 6,
    "ClinSigSimple": 7,
    "LastEvaluated": 8,
    "RS#": 9,  # dbSNP rsID
    "nsv/esv": 10,
    "RCVaccession": 11,
    "PhenotypeIDS": 12,
    "PhenotypeList": 13,
    "Origin": 14,
    "OriginSimple": 15,
    "Assembly": 16,
    "ChromosomeAccession": 17,
    "Chromosome": 18,
    "Start": 19,
    "Stop": 20,
    "ReferenceAllele": 21,
    "AlternateAllele": 22,
    "Cytogenetic": 23,
    "ReviewStatus": 24,
    "NumberSubmitters": 25,
    "Guidelines": 26,
    "TestedInGTR": 27,
    "OtherIDs": 28,
    "SubmitterCategories": 29,
    "VariationID": 30,
    "PositionVCF": 31,
    "ReferenceAlleleVCF": 32,
    "AlternateAlleleVCF": 33,
    # Added with the 2024 germline/somatic split; absent from older files.
    "SomaticClinicalImpact": 34,
    "SomaticClinicalImpactLastEvaluated": 35,
    "ReviewStatusClinicalImpact": 36,
    "Oncogenicity": 37,
    "OncogenicityLastEvaluated": 38,
    "ReviewStatusOncogenicity": 39,
}

# The header spellings NCBI uses for the columns whose names differ from the
# keys above.
_HEADER_NAMES = {"RS#": "RS# (dbSNP)", "nsv/esv": "nsv/esv (dbVar)"}

# What ``clinical_significance`` holds, by source format. With the somatic
# columns present it is the aggregate germline classification; without them
# the file predates the split and the column mixed germline and somatic
# assertions, which no later field can separate.
CLASSIFICATION_GERMLINE = "germline"
CLASSIFICATION_UNSPLIT = "unsplit"


def _column_map(header_line: str) -> Dict[str, int]:
    """Column indices for this file: documented index, overridden by name."""
    names = [h.strip() for h in header_line.lstrip("#").rstrip("\n").split("\t")]
    names[0] = "#" + names[0] if not names[0].startswith("#") else names[0]
    by_name = {name: i for i, name in enumerate(names)}
    columns = dict(CLINVAR_COLUMNS)
    for key in CLINVAR_COLUMNS:
        name = _HEADER_NAMES.get(key, key)
        if name in by_name:
            columns[key] = by_name[name]
        elif key in by_name:
            columns[key] = by_name[key]
        else:
            columns[key] = None  # an absent column must not read a neighbour
    for required in ("#AlleleID", "Assembly", "RS#", "GeneSymbol", "ClinicalSignificance", "PhenotypeList", "ReviewStatus"):
        if columns[required] is None:
            raise ValueError(f"ClinVar header missing required column: {required}")
    return columns


def _allele(fields, index: int) -> str:
    """Read an allele column; '' for missing, 'na', or '-' placeholders."""
    if index is None or index >= len(fields):
        return ""
    value = fields[index].strip().upper()
    return "" if value in ("", "NA", "-", ".") else value


def _source_value(fields, column, columns=None):
    index = (columns or CLINVAR_COLUMNS).get(column)
    if index is None:
        return None  # column not in this file: unknown, not empty
    value = fields[index].strip() if index < len(fields) else ""
    return None if value in ("", "na", "NA", "-", ".", "-1") else value


def _position(fields, columns=None):
    try:
        value = int(_source_value(fields, "PositionVCF", columns))
        return value if 0 < value < 2**63 else None
    except (TypeError, ValueError):
        return None


def _count(fields, column, columns=None):
    try:
        return int(_source_value(fields, column, columns))
    except (TypeError, ValueError):
        return None


def _bit(bitmap: bytearray, allele_id: str) -> bool:
    try:
        n = int(allele_id)
    except ValueError:
        return False
    byte = n >> 3
    return byte < len(bitmap) and bool(bitmap[byte] & (1 << (n & 7)))


def _allele_ids_with_grch38(path: Path, open_func, mode: str) -> bytearray:
    """Bitmap over AlleleID of the alleles that have a GRCh38 line."""
    bitmap = bytearray(1 << 20)  # grows as needed; AlleleIDs are a few million
    assembly_index, allele_index = CLINVAR_COLUMNS["Assembly"], CLINVAR_COLUMNS["#AlleleID"]
    with open_func(path, mode, encoding='utf-8') as f:
        for line in f:
            if line.startswith("#"):
                columns = _column_map(line)
                assembly_index, allele_index = columns["Assembly"], columns["#AlleleID"]
                continue
            fields = line.split('\t', max(assembly_index, allele_index) + 1)
            if len(fields) <= max(assembly_index, allele_index):
                continue
            if fields[assembly_index].strip() != "GRCh38":
                continue
            try:
                n = int(fields[allele_index])
            except ValueError:
                continue
            byte = n >> 3
            if byte >= len(bitmap):
                bitmap.extend(b"\0" * (byte + 1 - len(bitmap) + (1 << 20)))
            bitmap[byte] |= 1 << (n & 7)
    return bitmap


def parse_clinvar(filepath: str) -> Generator[Dict[str, Any], None, None]:
    """Parse ClinVar variant_summary.txt.gz file.
    
    Args:
        filepath: Path to variant_summary.txt.gz file
    
    Yields:
        Dict with keys: rsid, ref_allele, alt_allele, gene,
        clinical_significance, classification_type, conditions,
        condition_ids, review_status, last_evaluated, origin, origin_simple,
        rcv_accessions, number_submitters, variant_type, name, and the
        somatic clinical impact and oncogenicity classifications with their
        review statuses and dates (None when the file predates them).
        ``condition_ids`` is ClinVar's PhenotypeIDS column
        verbatim: identifiers for each entry of PhenotypeList, in the same
        order, so a condition can be resolved by MONDO identifier rather
        than by name (see allelio/analysis/inheritance.py); it is '' when
        ClinVar gives none, never None, so a stored row is never mistaken
        for one from a database built before the column existed. Alleles come
        from the VCF-style columns (forward strand of the
        reference build, the same convention consumer genotype files use);
        they are '' when ClinVar gives "na", which happens for large or
        complex variants.
    """
    path = Path(filepath)
    
    # Determine if file is gzipped
    open_func = gzip.open if filepath.endswith('.gz') else open
    mode = 'rt' if filepath.endswith('.gz') else 'r'

    # ClinVar lists each allele once per assembly. The VCF-style allele
    # columns of the GRCh37 line are not always trustworthy (rs6025's GRCh37
    # line reads T/T where GRCh38 reads C/T), so when both builds are present
    # only the GRCh38 line is emitted; a GRCh37-only allele is emitted as is.
    # The two lines are not reliably adjacent, so a first pass collects the
    # AlleleIDs that have a GRCh38 line (a bitmap, a few hundred KB).
    has_grch38 = _allele_ids_with_grch38(path, open_func, mode)

    columns = dict(CLINVAR_COLUMNS)
    classification_type = "unknown"
    with open_func(path, mode, encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            # The header decides where each column is and which format this is
            if line.startswith("#"):
                columns = _column_map(line)
                classification_type = (
                    CLASSIFICATION_GERMLINE if columns.get("SomaticClinicalImpact") is not None
                    else CLASSIFICATION_UNSPLIT
                )
                continue
            
            # Strip whitespace and split on tabs
            fields = line.rstrip('\n').split('\t')
            
            # Ensure we have enough fields
            if len(fields) <= columns["ReviewStatus"]:
                continue
            
            try:
                # Extract fields
                allele_id = fields[columns["#AlleleID"]].strip()
                rs_num = fields[columns["RS#"]].strip()
                gene_symbol = fields[columns["GeneSymbol"]].strip()
                clinical_sig = fields[columns["ClinicalSignificance"]].strip()
                phenotype_list = fields[columns["PhenotypeList"]].strip()
                phenotype_ids = (fields[columns["PhenotypeIDS"]].strip()
                                 if columns.get("PhenotypeIDS") is not None else None)
                review_status = _source_value(fields, "ReviewStatus", columns) or ""
                last_evaluated = _source_value(fields, "LastEvaluated", columns) or ""
                assembly = fields[columns["Assembly"]].strip()
                ref_allele = _allele(fields, columns["ReferenceAlleleVCF"])
                alt_allele = _allele(fields, columns["AlternateAlleleVCF"])
                
                # Filter: must have an rsID (not "-1")
                if rs_num == "-1" or not rs_num:
                    continue
                
                # Filter: only GRCh37 or GRCh38
                if assembly not in ("GRCh37", "GRCh38"):
                    continue
                
                # Convert rsID
                rsid = "rs" + rs_num if not rs_num.startswith("rs") else rs_num
                
                # Create record
                record = {
                    "rsid": rsid,
                    "assembly": assembly,
                    "chromosome": _source_value(fields, "Chromosome", columns),
                    "position_vcf": _position(fields, columns),
                    "allele_id": _source_value(fields, "#AlleleID", columns),
                    "variation_id": _source_value(fields, "VariationID", columns),
                    "hgnc_id": _source_value(fields, "HGNC_ID", columns),
                    "ref_allele": ref_allele,
                    "alt_allele": alt_allele,
                    "gene": gene_symbol if gene_symbol else None,
                    "clinical_significance": clinical_sig if clinical_sig else None,
                    "classification_type": classification_type,
                    "conditions": phenotype_list if phenotype_list else None,
                    "condition_ids": phenotype_ids,
                    "review_status": review_status if review_status else None,
                    "last_evaluated": last_evaluated if last_evaluated else None,
                    # Context for reading the classification: where the
                    # variant was observed, which per-condition records
                    # (RCVs) it aggregates, and how many submitters.
                    "origin": _source_value(fields, "Origin", columns),
                    "origin_simple": _source_value(fields, "OriginSimple", columns),
                    "rcv_accessions": _source_value(fields, "RCVaccession", columns),
                    "number_submitters": _count(fields, "NumberSubmitters", columns),
                    "variant_type": _source_value(fields, "Type", columns),
                    "name": _source_value(fields, "Name", columns),
                    # The somatic classifications, separate from the germline
                    # one; None when the column is absent (older format) or
                    # ClinVar gives "-" (no somatic assertion).
                    "somatic_clinical_impact": _source_value(fields, "SomaticClinicalImpact", columns),
                    "somatic_review_status": _source_value(fields, "ReviewStatusClinicalImpact", columns),
                    "somatic_last_evaluated": _source_value(fields, "SomaticClinicalImpactLastEvaluated", columns),
                    "oncogenicity": _source_value(fields, "Oncogenicity", columns),
                    "oncogenicity_review_status": _source_value(fields, "ReviewStatusOncogenicity", columns),
                    "oncogenicity_last_evaluated": _source_value(fields, "OncogenicityLastEvaluated", columns),
                }

                if assembly == "GRCh37" and _bit(has_grch38, allele_id):
                    continue  # the GRCh38 line for this allele is the one kept
                yield record
                
            except (IndexError, ValueError):
                # Skip malformed lines
                continue
