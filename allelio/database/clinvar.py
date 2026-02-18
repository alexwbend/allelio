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


def parse_clinvar(filepath: str) -> Generator[Dict[str, Any], None, None]:
    """Parse ClinVar variant_summary.txt.gz file.
    
    Args:
        filepath: Path to variant_summary.txt.gz file
    
    Yields:
        Dict with keys: rsid, gene, clinical_significance, conditions, review_status, last_evaluated
    """
    path = Path(filepath)
    
    # Determine if file is gzipped
    open_func = gzip.open if filepath.endswith('.gz') else open
    mode = 'rt' if filepath.endswith('.gz') else 'r'
    
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
                rs_num = fields[CLINVAR_COLUMNS["RS#"]].strip()
                gene_symbol = fields[CLINVAR_COLUMNS["GeneSymbol"]].strip()
                clinical_sig = fields[CLINVAR_COLUMNS["ClinicalSignificance"]].strip()
                phenotype_list = fields[CLINVAR_COLUMNS["PhenotypeList"]].strip()
                review_status = fields[CLINVAR_COLUMNS["ReviewStatus"]].strip()
                last_evaluated = fields[CLINVAR_COLUMNS["LastEvaluated"]].strip()
                assembly = fields[CLINVAR_COLUMNS["Assembly"]].strip()
                
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
                    "gene": gene_symbol if gene_symbol else None,
                    "clinical_significance": clinical_sig if clinical_sig else None,
                    "conditions": phenotype_list if phenotype_list else None,
                    "review_status": review_status if review_status else None,
                    "last_evaluated": last_evaluated if last_evaluated else None,
                }
                
                yield record
                
            except (IndexError, ValueError):
                # Skip malformed lines
                continue
