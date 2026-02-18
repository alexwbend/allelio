"""GWAS Catalog reference database parser."""

from typing import Generator, Dict, Any, Optional
from pathlib import Path


def parse_gwas(filepath: str) -> Generator[Dict[str, Any], None, None]:
    """Parse GWAS associations TSV file.
    
    Args:
        filepath: Path to GWAS associations file
    
    Yields:
        Dict with keys: rsid, trait, p_value, odds_ratio, mapped_gene, study, pubmed_id, link
    """
    path = Path(filepath)
    
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        # Read header
        header = f.readline().rstrip('\n').split('\t')
        
        # Find column indices
        col_indices = {}
        for col_name in ["SNPS", "SNP_ID_CURRENT", "DISEASE/TRAIT", "P-VALUE", 
                         "OR or BETA", "MAPPED_GENE", "STUDY", "PUBMEDID", "LINK"]:
            try:
                col_indices[col_name] = header.index(col_name)
            except ValueError:
                col_indices[col_name] = None
        
        # Parse data lines
        for line_num, line in enumerate(f, 2):
            fields = line.rstrip('\n').split('\t')
            
            # Ensure we have enough fields
            if len(fields) < max(idx for idx in col_indices.values() if idx is not None):
                continue
            
            try:
                # Extract rsID - prefer SNP_ID_CURRENT, fall back to SNPS
                rsid = None
                if col_indices["SNP_ID_CURRENT"] is not None:
                    rsid_field = fields[col_indices["SNP_ID_CURRENT"]].strip()
                    if rsid_field and rsid_field != "-":
                        rsid = rsid_field
                
                if not rsid and col_indices["SNPS"] is not None:
                    rsid_field = fields[col_indices["SNPS"]].strip()
                    if rsid_field and rsid_field != "-":
                        rsid = rsid_field
                
                # Skip if no valid rsID
                if not rsid:
                    continue
                
                # Ensure rsID has "rs" prefix
                if not rsid.startswith("rs"):
                    rsid = "rs" + rsid
                
                # Extract other fields
                trait = ""
                if col_indices["DISEASE/TRAIT"] is not None:
                    trait = fields[col_indices["DISEASE/TRAIT"]].strip()
                
                p_value = None
                if col_indices["P-VALUE"] is not None:
                    p_val_str = fields[col_indices["P-VALUE"]].strip()
                    if p_val_str and p_val_str != "-":
                        try:
                            p_value = float(p_val_str)
                        except ValueError:
                            pass
                
                odds_ratio = None
                if col_indices["OR or BETA"] is not None:
                    odds_ratio = fields[col_indices["OR or BETA"]].strip()
                    if not odds_ratio or odds_ratio == "-":
                        odds_ratio = None
                
                mapped_gene = None
                if col_indices["MAPPED_GENE"] is not None:
                    mapped_gene = fields[col_indices["MAPPED_GENE"]].strip()
                    if not mapped_gene or mapped_gene == "-":
                        mapped_gene = None
                
                study = None
                if col_indices["STUDY"] is not None:
                    study = fields[col_indices["STUDY"]].strip()
                    if not study or study == "-":
                        study = None
                
                pubmed_id = None
                if col_indices["PUBMEDID"] is not None:
                    pubmed_id = fields[col_indices["PUBMEDID"]].strip()
                    if not pubmed_id or pubmed_id == "-":
                        pubmed_id = None
                
                link = None
                if col_indices["LINK"] is not None:
                    link = fields[col_indices["LINK"]].strip()
                    if not link or link == "-":
                        link = None
                
                # Create record
                record = {
                    "rsid": rsid,
                    "trait": trait if trait else None,
                    "p_value": p_value,
                    "odds_ratio": odds_ratio,
                    "mapped_gene": mapped_gene,
                    "study": study,
                    "pubmed_id": pubmed_id,
                    "link": link,
                }
                
                yield record
                
            except (IndexError, ValueError):
                # Skip malformed lines
                continue
