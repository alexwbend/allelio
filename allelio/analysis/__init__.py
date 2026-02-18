"""Allelio analysis module."""

from .lookup import (
    ClinVarEntry,
    GWASEntry,
    VariantResult,
    VariantCategory,
    analyze_variants,
    SIGNIFICANCE_RANKS,
    HIGH_IMPACT_GENES,
)

__all__ = [
    "ClinVarEntry",
    "GWASEntry",
    "VariantResult",
    "VariantCategory",
    "analyze_variants",
    "SIGNIFICANCE_RANKS",
    "HIGH_IMPACT_GENES",
]
