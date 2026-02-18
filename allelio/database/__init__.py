"""Allelio database module."""

from .store import AllelioDB
from .downloader import download_file, setup_database
from .clinvar import parse_clinvar
from .gwas import parse_gwas

__all__ = [
    "AllelioDB",
    "download_file",
    "setup_database",
    "parse_clinvar",
    "parse_gwas",
]
