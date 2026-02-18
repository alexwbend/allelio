"""VCF (Variant Call Format) genotype file parser.

This module parses genotype files in VCF format (Variant Call Format v4.2+).

Format specification:
- Tab-delimited file with required columns: CHROM, POS, ID, REF, ALT, QUAL, FILTER, INFO, FORMAT
- Meta-info lines start with '##' (skipped)
- Header line starts with '#CHROM' (defines columns)
- Data lines contain variant information
- Genotype extracted from first sample column's GT field
- GT field values like '0/1' are converted to actual alleles using REF and ALT
- Pure Python implementation with no external dependencies
"""

import gzip
from typing import List, Generator, Optional, Tuple

from .base import Variant


def _parse_gt_field(gt_str: str, ref: str, alt: str) -> Optional[str]:
    """Convert VCF GT field to genotype string using REF and ALT alleles.
    
    Args:
        gt_str: Genotype field value (e.g., "0/1", "1/1", ".|.", "./.")
        ref: Reference allele sequence
        alt: Comma-separated alternate allele sequences
        
    Returns:
        Genotype string (e.g., "AT", "TT") or None if no-call
    """
    # Split on | or /
    separator = '|' if '|' in gt_str else '/'
    
    try:
        alleles_str = gt_str.split(':')[0]  # Get GT part before any other fields
        allele_indices = alleles_str.split(separator)
    except (ValueError, IndexError):
        return None
    
    # Parse alternate alleles
    alt_list = alt.split(',') if alt else []
    
    # Convert alleles
    genotype_alleles = []
    for allele_idx in allele_indices:
        # Skip missing alleles (. or empty)
        if allele_idx in ('.', ''):
            return None
        
        try:
            idx = int(allele_idx)
            if idx == 0:
                genotype_alleles.append(ref)
            elif idx > 0 and idx <= len(alt_list):
                genotype_alleles.append(alt_list[idx - 1])
            else:
                return None
        except ValueError:
            return None
    
    # Return combined genotype
    if len(genotype_alleles) == 2:
        return ''.join(sorted(genotype_alleles))
    elif len(genotype_alleles) == 1:
        return genotype_alleles[0] * 2  # Haploid to diploid
    else:
        return None


def _parse_vcf_lines(filepath: str) -> Generator[Variant, None, None]:
    """Generate Variant objects from a VCF format file.
    
    Args:
        filepath: Path to the VCF format file (can be gzipped)
        
    Yields:
        Variant objects for each valid variant in the file
    """
    # Open file with gzip if needed
    file_opener = gzip.open if filepath.endswith('.gz') else open
    
    with file_opener(filepath, 'rt', encoding='utf-8', errors='replace') as f:
        header_line = None
        format_index = None
        sample_column_index = None
        gt_index = None
        
        for line in f:
            line = line.rstrip('\n')
            
            # Skip empty lines
            if not line:
                continue
            
            # Skip meta-info lines
            if line.startswith('##'):
                continue
            
            # Parse header line
            if line.startswith('#CHROM'):
                header_line = line
                parts = line[1:].split('\t')  # Remove leading #
                
                try:
                    # Find required column indices
                    chrom_index = parts.index('CHROM')
                    pos_index = parts.index('POS')
                    id_index = parts.index('ID')
                    ref_index = parts.index('REF')
                    alt_index = parts.index('ALT')
                    format_index = parts.index('FORMAT')
                    
                    # Sample column is the first column after FORMAT
                    sample_column_index = format_index + 1
                except ValueError:
                    continue
                
                continue
            
            # Skip other comment lines
            if line.startswith('#'):
                continue
            
            # Parse data line
            if header_line is None:
                continue
            
            parts = line.split('\t')
            
            if len(parts) < format_index + 2:
                continue
            
            try:
                chromosome = parts[chrom_index]
                position = int(parts[pos_index])
                rsid = parts[id_index]
                ref = parts[ref_index]
                alt = parts[alt_index]
                format_field = parts[format_index]
                sample_data = parts[sample_column_index]
                
                # Skip if no rsid
                if rsid == '.':
                    continue
                
                # Parse FORMAT to find GT index
                format_parts = format_field.split(':')
                try:
                    gt_index = format_parts.index('GT')
                except ValueError:
                    continue
                
                # Parse sample GT field
                sample_parts = sample_data.split(':')
                if gt_index >= len(sample_parts):
                    continue
                
                gt_str = sample_parts[gt_index]
                genotype = _parse_gt_field(gt_str, ref, alt)
                
                # Skip no-calls
                if genotype is None:
                    continue
                
                # Yield valid variant
                yield Variant(
                    rsid=rsid,
                    chromosome=chromosome,
                    position=position,
                    genotype=genotype
                )
            
            except (ValueError, IndexError):
                continue


def parse_vcf(filepath: str) -> List[Variant]:
    """Parse a VCF format genotype file.
    
    Args:
        filepath: Path to the VCF format file (can be gzipped)
        
    Returns:
        List of Variant objects parsed from the file
    """
    return list(_parse_vcf_lines(filepath))
