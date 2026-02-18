"""23andMe format genotype file parser.

This module parses genotype files from 23andMe in their standard tab-delimited format.

Format specification:
- Tab-delimited file with 4 columns
- Columns: rsid, chromosome, position, genotype
- Comment lines start with '#'
- No-calls are represented as '--' and are skipped
- Valid rsid format starts with 'rs' or 'i'
"""

import gzip
from typing import List, Generator

from .base import Variant


def _parse_23andme_lines(filepath: str) -> Generator[Variant, None, None]:
    """Generate Variant objects from a 23andMe format file.
    
    Args:
        filepath: Path to the 23andMe format file (can be gzipped)
        
    Yields:
        Variant objects for each valid line in the file
    """
    # Open file with gzip if needed
    file_opener = gzip.open if filepath.endswith('.gz') else open
    
    with file_opener(filepath, 'rt', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.rstrip('\n')
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Parse tab-delimited line
            parts = line.split('\t')
            if len(parts) < 4:
                continue
            
            rsid, chromosome, position_str, genotype = parts[0], parts[1], parts[2], parts[3]
            
            # Validate rsid format (must start with 'rs' or 'i')
            if not (rsid.startswith('rs') or rsid.startswith('i')):
                continue
            
            # Skip no-calls
            if genotype == '--':
                continue
            
            # Parse position as integer
            try:
                position = int(position_str)
            except ValueError:
                continue
            
            # Yield valid variant
            yield Variant(
                rsid=rsid,
                chromosome=chromosome,
                position=position,
                genotype=genotype
            )


def parse_23andme(filepath: str) -> List[Variant]:
    """Parse a 23andMe format genotype file.
    
    Args:
        filepath: Path to the 23andMe format file (can be gzipped)
        
    Returns:
        List of Variant objects parsed from the file
    """
    return list(_parse_23andme_lines(filepath))
