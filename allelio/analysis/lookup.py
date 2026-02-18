"""Variant lookup and analysis engine."""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

from allelio.database.store import AllelioDB


# Significance ranking for clinical significance strings
SIGNIFICANCE_RANKS = {
    "pathogenic": 1,
    "likely pathogenic": 2,
    "pathogenic/likely pathogenic": 2,
    "risk factor": 3,
    "association": 4,
    "protective": 5,
    "conflicting data": 6,
    "conflicting interpretations": 6,
    "uncertain significance": 7,
    "likely benign": 8,
    "benign": 10,
    "benign/likely benign": 10,
}

# High-impact genes requiring special attention
HIGH_IMPACT_GENES = {
    "BRCA1", "BRCA2", "APOE", "TP53", "MLH1", "MSH2", "MSH6", "PMS2",
    "APC", "MUTYH", "CDKN2A", "STK11", "PTEN", "RB1", "CHEK2",
    "PALB2", "RAD51C", "RAD51D", "BARD1", "ATM", "NF1", "VHL",
    "SDHA", "SDHB", "SDHC", "SDHD", "LDLR", "PCSK9", "APOB"
}


class VariantCategory(str, Enum):
    """Categories for variant classification."""
    HEALTH_CONDITIONS = "Health Conditions"
    RISK_FACTORS = "Risk Factors"
    PHARMACOGENOMICS = "Pharmacogenomics"
    TRAITS = "Traits"
    CARRIER_STATUS = "Carrier Status"
    UNKNOWN = "Unknown"


@dataclass
class ClinVarEntry:
    """ClinVar variant entry."""
    rsid: str
    gene: Optional[str] = None
    clinical_significance: Optional[str] = None
    conditions: Optional[str] = None
    review_status: Optional[str] = None


@dataclass
class GWASEntry:
    """GWAS association entry."""
    rsid: str
    trait: Optional[str] = None
    p_value: Optional[float] = None
    odds_ratio: Optional[str] = None
    mapped_gene: Optional[str] = None
    study: Optional[str] = None
    pubmed_id: Optional[str] = None


@dataclass
class VariantResult:
    """Result of variant analysis."""
    rsid: str
    chromosome: Optional[str] = None
    position: Optional[int] = None
    genotype: Optional[str] = None
    clinvar_entries: List[ClinVarEntry] = field(default_factory=list)
    gwas_entries: List[GWASEntry] = field(default_factory=list)
    category: str = VariantCategory.UNKNOWN.value
    significance_rank: int = 999


def _determine_category(clinvar_entry: Optional[ClinVarEntry], gwas_entries: List[GWASEntry]) -> str:
    """Determine variant category based on annotations.
    
    Args:
        clinvar_entry: ClinVar entry if available
        gwas_entries: List of GWAS entries
    
    Returns:
        Category string
    """
    if clinvar_entry:
        sig = (clinvar_entry.clinical_significance or "").lower()

        # Check for health conditions (pathogenic/likely pathogenic)
        if any(x in sig for x in ["pathogenic", "likely pathogenic"]):
            return VariantCategory.HEALTH_CONDITIONS.value

        # Check for risk factors
        if any(x in sig for x in ["risk factor", "risk_factor", "association"]):
            return VariantCategory.RISK_FACTORS.value

        # Check for carrier status / benign
        if "likely benign" in sig or "benign" in sig:
            return VariantCategory.CARRIER_STATUS.value
    
    # Check GWAS for pharmacogenomics
    if gwas_entries:
        for entry in gwas_entries:
            trait = (entry.trait or "").lower()
            if any(x in trait for x in ["drug", "pharmacogenom", "medication", "response"]):
                return VariantCategory.PHARMACOGENOMICS.value
            
            # Check for risk factor
            if "risk" in trait or "association" in trait:
                return VariantCategory.RISK_FACTORS.value
        
        # Default to traits if only GWAS data
        return VariantCategory.TRAITS.value
    
    return VariantCategory.UNKNOWN.value


def _get_significance_rank(clinical_significance: Optional[str]) -> int:
    """Get numeric significance rank from clinical significance string.
    
    Args:
        clinical_significance: Clinical significance string
    
    Returns:
        Numeric rank (lower = more significant)
    """
    if not clinical_significance:
        return 999
    
    sig_lower = clinical_significance.lower()
    
    # Exact matches take priority
    for key, rank in SIGNIFICANCE_RANKS.items():
        if sig_lower == key:
            return rank
    
    # Substring matches
    for key, rank in SIGNIFICANCE_RANKS.items():
        if key in sig_lower:
            return rank
    
    return 999


def analyze_variants(
    variants: List[Any],
    db: AllelioDB,
    include_benign: bool = False
) -> List[VariantResult]:
    """Analyze variants against reference databases.
    
    Args:
        variants: List of Variant objects with rsid attribute
        db: AllelioDB database instance
        include_benign: Whether to include benign variants in results
    
    Returns:
        List of VariantResult objects sorted by significance rank
    """
    if not variants:
        return []
    
    # Extract rsIDs from variant objects
    rsids = [getattr(v, 'rsid', str(v)) for v in variants]
    rsids = [r for r in rsids if r]  # Filter empty rsids
    
    if not rsids:
        return []
    
    # Create mapping of rsid to original variant for metadata
    rsid_to_variant = {
        getattr(v, 'rsid', str(v)): v for v in variants
    }
    
    # Batch lookup from database
    lookup_results = db.lookup_rsids_batch(rsids)
    
    # Build results
    results = []
    
    for rsid, data in lookup_results.items():
        if not data["clinvar"] and not data["gwas"]:
            continue
        
        # Create ClinVar entry
        clinvar_entry = None
        if data["clinvar"]:
            cv_data = data["clinvar"][0]
            clinvar_entry = ClinVarEntry(
                rsid=cv_data.get("rsid"),
                gene=cv_data.get("gene"),
                clinical_significance=cv_data.get("clinical_significance"),
                conditions=cv_data.get("conditions"),
                review_status=cv_data.get("review_status")
            )
        
        # Create GWAS entries
        gwas_entries = []
        for gw_data in data["gwas"]:
            gwas_entries.append(GWASEntry(
                rsid=gw_data.get("rsid"),
                trait=gw_data.get("trait"),
                p_value=gw_data.get("p_value"),
                odds_ratio=gw_data.get("odds_ratio"),
                mapped_gene=gw_data.get("mapped_gene"),
                study=gw_data.get("study"),
                pubmed_id=gw_data.get("pubmed_id")
            ))
        
        # Determine category
        category = _determine_category(clinvar_entry, gwas_entries)
        
        # Get significance rank from ClinVar
        sig_rank = 999
        if clinvar_entry and clinvar_entry.clinical_significance:
            sig_rank = _get_significance_rank(clinvar_entry.clinical_significance)
        elif gwas_entries:
            # For GWAS-only variants, use a default rank
            sig_rank = SIGNIFICANCE_RANKS.get("association", 4)
        
        # Skip benign variants unless requested
        if not include_benign and sig_rank >= 8:
            continue
        
        # Get variant metadata
        original_variant = rsid_to_variant.get(rsid)
        chromosome = getattr(original_variant, 'chromosome', None)
        position = getattr(original_variant, 'position', None)
        genotype = getattr(original_variant, 'genotype', None)
        
        # Create result
        result = VariantResult(
            rsid=rsid,
            chromosome=chromosome,
            position=position,
            genotype=genotype,
            clinvar_entries=[clinvar_entry] if clinvar_entry else [],
            gwas_entries=gwas_entries,
            category=category,
            significance_rank=sig_rank
        )
        
        results.append(result)
    
    # Sort by significance rank (lower = more significant)
    results.sort(key=lambda x: x.significance_rank)
    
    return results
