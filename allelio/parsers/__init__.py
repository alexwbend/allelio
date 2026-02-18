"""Allelio genotype file parsers.

This package provides parsers for multiple genotype file formats:
- 23andMe: Tab-delimited format with rsid, chromosome, position, genotype
- AncestryDNA: Tab-delimited format with rsid, chromosome, position, and allele(s)
- VCF: Standard Variant Call Format

Main API:
- parse_genotype_file(filepath): Auto-detect format and parse file
- detect_format(filepath): Detect file format without parsing
- Variant: Dataclass for representing a parsed variant
"""

from .base import Variant, parse_genotype_file, detect_format
from .twentythree import parse_23andme
from .ancestry import parse_ancestry
from .vcf_parser import parse_vcf

__all__ = [
    'Variant',
    'parse_genotype_file',
    'detect_format',
    'parse_23andme',
    'parse_ancestry',
    'parse_vcf',
]
