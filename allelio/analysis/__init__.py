"""Allelio analysis module."""

from .zygosity import Zygosity, ZygosityCall, call_zygosity
from .lookup import (
    ClinVarEntry,
    ClinGenEntry,
    PGxEntry,
    GWASEntry,
    VariantResult,
    VariantCategory,
    analyze_variants,
    analyze_variants_with_stats,
    AnalysisStats,
    AnalysisResults,
    SIGNIFICANCE_RANKS,
    REVIEW_STATUS_STARS,
    HIGH_IMPACT_GENES,
    _get_review_stars,
)

__all__ = [
    "ClinVarEntry",
    "ClinGenEntry",
    "PGxEntry",
    "GWASEntry",
    "VariantResult",
    "VariantCategory",
    "analyze_variants",
    "analyze_variants_with_stats",
    "AnalysisStats",
    "AnalysisResults",
    "Zygosity",
    "ZygosityCall",
    "call_zygosity",
    "SIGNIFICANCE_RANKS",
    "REVIEW_STATUS_STARS",
    "HIGH_IMPACT_GENES",
    "_get_review_stars",
]
