"""Allelio analysis module."""

from .lookup import (
    ClinVarEntry,
    GWASEntry,
    VariantResult,
    VariantCategory,
    analyze_variants,
    SIGNIFICANCE_RANKS,
    REVIEW_STATUS_STARS,
    HIGH_IMPACT_GENES,
    _get_review_stars,
)

__all__ = [
    "ClinVarEntry",
    "GWASEntry",
    "VariantResult",
    "VariantCategory",
    "analyze_variants",
    "SIGNIFICANCE_RANKS",
    "REVIEW_STATUS_STARS",
    "HIGH_IMPACT_GENES",
    "_get_review_stars",
]
