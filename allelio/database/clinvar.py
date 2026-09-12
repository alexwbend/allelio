"""ClinVar reference database parser."""

import gzip
from typing import Generator, Dict, Any, Optional
from pathlib import Path


# ClinVar variant_summary.txt column indices
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
}


def _allele(fields, index: int) -> str:
    """Read an allele column; '' for missing, 'na', or '-' placeholders."""
    if index >= len(fields):
        return ""
    value = fields[index].strip().upper()
    return "" if value in ("", "NA", "-", ".") else value


def _source_value(fields, column):
    index = CLINVAR_COLUMNS[column]
    value = fields[index].strip() if index < len(fields) else ""
    return None if value in ("", "na", "NA", "-", ".", "-1") else value


def _position(fields):
    try:
        value = int(_source_value(fields, "PositionVCF"))
        return value if 0 < value < 2**63 else None
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
    with open_func(path, mode, encoding='utf-8') as f:
        for line in f:
            if line.startswith("#AlleleID"):
                continue
            fields = line.split('\t', 17)
            if len(fields) <= CLINVAR_COLUMNS["Assembly"]:
                continue
            if fields[CLINVAR_COLUMNS["Assembly"]].strip() != "GRCh38":
                continue
            try:
                n = int(fields[0])
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
        clinical_significance, conditions, condition_ids, review_status,
        last_evaluated. ``condition_ids`` is ClinVar's PhenotypeIDS column
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

    with open_func(path, mode, encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            # Skip header line
            if line.startswith("#AlleleID"):
                continue
            
            # Strip whitespace and split on tabs
            fields = line.rstrip('\n').split('\t')
            
            # Ensure we have enough fields
            if len(fields) <= CLINVAR_COLUMNS["ReviewStatus"]:
                continue
            
            try:
                # Extract fields
                allele_id = fields[CLINVAR_COLUMNS["#AlleleID"]].strip()
                rs_num = fields[CLINVAR_COLUMNS["RS#"]].strip()
                gene_symbol = fields[CLINVAR_COLUMNS["GeneSymbol"]].strip()
                clinical_sig = fields[CLINVAR_COLUMNS["ClinicalSignificance"]].strip()
                phenotype_list = fields[CLINVAR_COLUMNS["PhenotypeList"]].strip()
                phenotype_ids = fields[CLINVAR_COLUMNS["PhenotypeIDS"]].strip()
                review_status = fields[CLINVAR_COLUMNS["ReviewStatus"]].strip()
                last_evaluated = fields[CLINVAR_COLUMNS["LastEvaluated"]].strip()
                assembly = fields[CLINVAR_COLUMNS["Assembly"]].strip()
                ref_allele = _allele(fields, CLINVAR_COLUMNS["ReferenceAlleleVCF"])
                alt_allele = _allele(fields, CLINVAR_COLUMNS["AlternateAlleleVCF"])
                
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
                    "chromosome": _source_value(fields, "Chromosome"),
                    "position_vcf": _position(fields),
                    "allele_id": _source_value(fields, "#AlleleID"),
                    "variation_id": _source_value(fields, "VariationID"),
                    "hgnc_id": _source_value(fields, "HGNC_ID"),
                    "ref_allele": ref_allele,
                    "alt_allele": alt_allele,
                    "gene": gene_symbol if gene_symbol else None,
                    "clinical_significance": clinical_sig if clinical_sig else None,
                    "conditions": phenotype_list if phenotype_list else None,
                    "condition_ids": phenotype_ids,
                    "review_status": review_status if review_status else None,
                    "last_evaluated": last_evaluated if last_evaluated else None,
                }

                if assembly == "GRCh37" and _bit(has_grch38, allele_id):
                    continue  # the GRCh38 line for this allele is the one kept
                yield record
                
            except (IndexError, ValueError):
                # Skip malformed lines
                continue
