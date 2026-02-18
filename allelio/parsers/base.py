"""Base parser module for Allelio genotype files.

This module provides:
- Variant dataclass for storing genotype information
- Format detection function
- Main entry point for parsing files
"""

import gzip
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class Variant:
    """Represents a genetic variant with genotype information.

    Attributes:
        rsid: Reference SNP ID (e.g., "rs12345" or "i123")
        chromosome: Chromosome number or name (e.g., "1", "X", "MT")
        position: Physical position on chromosome (1-based)
        genotype: Genotype string (e.g., "AA", "AT", "TT", "--")
    """
    rsid: str
    chromosome: str
    position: int
    genotype: str


def detect_format(filepath: str) -> str:
    """Detect the format of a genotype file by examining the first few lines.

    Supports detection of:
    - 23andMe format: tab-delimited with rsid in first column, comment lines start with #
    - AncestryDNA format: tab-delimited with "rsid" header line
    - VCF format: lines starting with ## or single # header line

    Args:
        filepath: Path to the genotype file (can be gzipped)

    Returns:
        Format string: "23andme", "ancestry", "vcf"

    Raises:
        ValueError: If format cannot be detected
    """
    # Open file with gzip if needed
    file_opener = gzip.open if filepath.endswith('.gz') else open

    try:
        with file_opener(filepath, 'rt', encoding='utf-8', errors='replace') as f:
            lines = []
            for i in range(50):  # Read up to 50 lines (VCF can have many headers)
                line = f.readline()
                if not line:
                    break
                lines.append(line.rstrip('\n'))

            if not lines:
                raise ValueError("File is empty")

            # Check for VCF format (case-insensitive)
            for line in lines:
                if line.lower().startswith('##fileformat=vcf'):
                    return "vcf"

            # Check for VCF by looking for #CHROM header
            for line in lines:
                if line.startswith('#CHROM'):
                    return "vcf"

            # Check for non-comment lines
            first_non_comment = None
            for line in lines:
                if line and not line.startswith('#'):
                    first_non_comment = line
                    break

            if not first_non_comment:
                raise ValueError("No data lines found in file")

            # Check if it's a header line (AncestryDNA has "rsid" header)
            if first_non_comment.lower().startswith('rsid'):
                return "ancestry"

            # Check if it looks like 23andMe tab-delimited genotype data
            for line in lines:
                if line and not line.startswith('#'):
                    parts = line.split('\t')
                    if len(parts) >= 4:
                        try:
                            int(parts[2])  # Position should be numeric
                            if parts[0].startswith('rs') or parts[0].startswith('i'):
                                return "23andme"
                        except (ValueError, IndexError):
                            pass

            raise ValueError("Unable to determine file format")

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Unable to detect format: {str(e)}")


def parse_genotype_file(filepath: str) -> List[Variant]:
    """Parse a genotype file, auto-detecting the format.

    This function detects the file format and delegates to the appropriate
    parser module. Currently supports 23andMe, AncestryDNA, and VCF formats.

    Args:
        filepath: Path to the genotype file (can be gzipped)

    Returns:
        List of Variant objects parsed from the file

    Raises:
        ValueError: If format cannot be detected or parsing fails
        FileNotFoundError: If file does not exist
    """
    # Verify file exists
    if not Path(filepath).exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    # Detect format
    fmt = detect_format(filepath)

    # Delegate to appropriate parser
    if fmt == "23andme":
        from .twentythree import parse_23andme
        return parse_23andme(filepath)
    elif fmt == "ancestry":
        from .ancestry import parse_ancestry
        return parse_ancestry(filepath)
    elif fmt == "vcf":
        from .vcf_parser import parse_vcf
        return parse_vcf(filepath)
    else:
        raise ValueError(f"Unknown format: {fmt}")
