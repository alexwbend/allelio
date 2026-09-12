"""AncestryDNA format genotype file parser.

This module parses genotype files from AncestryDNA. The format supports both
4-column (rsid, chromosome, position, genotype) and 5-column 
(rsid, chromosome, position, allele1, allele2) variants.

Format specification:
- Tab-delimited file with 4 or 5 columns
- First line is a header starting with 'rsid' (skipped)
- Comment lines start with '#'
- No-calls represented as '00', '0', or '--' are skipped
- If 5 columns: allele1 and allele2 are combined into genotype string
- If 4 columns: genotype column is used directly
"""

import gzip
from typing import List, Generator

from .base import ParseAudit, ParsedVariants, Variant


def _parse_ancestry_lines(filepath: str, audit=None) -> Generator[Variant, None, None]:
    """Generate Variant objects from an AncestryDNA format file.
    
    Args:
        filepath: Path to the AncestryDNA format file (can be gzipped)
        
    Yields:
        Variant objects for each valid line in the file
    """
    # Open file with gzip if needed
    file_opener = gzip.open if filepath.endswith('.gz') else open
    
    with file_opener(filepath, 'rt', encoding='utf-8', errors='replace') as f:
        header_seen = False
        
        for line_number, line in enumerate(f, 1):
            line = line.rstrip('\r\n')
            
            # Skip empty lines and comments
            if not line.strip() or line.startswith('#'):
                continue
            
            # Skip header line (starts with 'rsid')
            if line.lower().startswith('rsid'):
                header_seen = True
                continue
            
            entry = audit.row(line_number) if audit is not None else {}

            # Parse tab-delimited line
            parts = line.split('\t')
            
            if len(parts) < 4:
                continue
            
            rsid = parts[0]
            chromosome = parts[1]
            position_str = parts[2]
            
            # Determine genotype based on number of columns
            if len(parts) == 4:
                # 4-column format: rsid, chromosome, position, genotype
                genotype = parts[3]
            elif len(parts) >= 5:
                # 5-column format: rsid, chromosome, position, allele1, allele2
                allele1 = parts[3]
                allele2 = parts[4]
                genotype = allele1 + allele2
            else:
                continue
            
            # Skip no-calls
            if genotype in ('00', '0', '--', '.', '') or '0' in genotype or '-' in genotype:
                entry['status'] = 'no_call'
                continue
            
            # Parse position as integer
            try:
                position = int(position_str)
            except ValueError:
                entry['status'] = 'invalid_position'
                continue
            if position <= 0:
                entry['status'] = 'invalid_position'
                continue
            
            entry.update(status='parsed', rsid=rsid)
            # Yield valid variant
            yield Variant(
                rsid=rsid,
                chromosome=chromosome,
                position=position,
                genotype=genotype,
                source_line=line_number,
            )


def parse_ancestry(filepath: str) -> List[Variant]:
    """Parse an AncestryDNA format genotype file.
    
    Supports both 4-column and 5-column variants of the format.
    
    Args:
        filepath: Path to the AncestryDNA format file (can be gzipped)
        
    Returns:
        List of Variant objects parsed from the file
    """
    audit = ParseAudit()
    return ParsedVariants(_parse_ancestry_lines(filepath, audit=audit), audit)
