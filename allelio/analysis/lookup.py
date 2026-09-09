"""Variant lookup and analysis engine."""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

from allelio.database.store import AllelioDB


# ClinVar review status to star rating mapping (0-4 stars)
# See: https://www.ncbi.nlm.nih.gov/clinvar/docs/review_status/
REVIEW_STATUS_STARS = {
    "practice guideline": 4,
    "reviewed by expert panel": 3,
    "criteria provided, multiple submitters, no conflicts": 2,
    "criteria provided, multiple submitters": 2,
    "criteria provided, conflicting interpretations": 1,
    "criteria provided, single submitter": 1,
    "no assertion for the individual variant": 0,
    "no assertion criteria provided": 0,
    "no assertion provided": 0,
}


def _get_review_stars(review_status: Optional[str]) -> int:
    """Convert ClinVar review status string to a 0-4 star rating.

    Args:
        review_status: ClinVar review status string

    Returns:
        Integer star rating from 0 (lowest confidence) to 4 (highest)
    """
    if not review_status:
        return 0

    status_lower = review_status.lower().strip()

    # Exact match first
    if status_lower in REVIEW_STATUS_STARS:
        return REVIEW_STATUS_STARS[status_lower]

    # Substring match for variations in formatting
    for key, stars in REVIEW_STATUS_STARS.items():
        if key in status_lower:
            return stars

    return 0


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
    "conflicting classifications of pathogenicity": 6,
    "uncertain significance": 7,
    "likely benign": 8,
    "benign": 10,
    "benign/likely benign": 10,
}

# --- Allele-frequency tiers used to adjust the rank ------------------------
# ACMG/AMP (Richards et al. 2015, https://doi.org/10.1038/gim.2015.30) treats
# population allele frequency as evidence against pathogenicity: BA1
# (stand-alone) at roughly 5%, BS1 (strong) at roughly 1%, for a fully
# penetrant dominant disorder. Those are the two cited cutoffs below. BA1/BS1
# are categorical evidence codes, not numeric rank penalties, so the tier
# boundaries are cited but the third, tighter tier and every penalty size
# below are Allelio's own choices, not a re-derivation of ACMG/AMP.
COMMON_AF_THRESHOLD = 0.05  # cf. ACMG/AMP BA1 (~5%), Richards et al. 2015
MODERATELY_COMMON_AF_THRESHOLD = 0.01  # cf. ACMG/AMP BS1 (~1%), Richards et al. 2015
UNCOMMON_AF_THRESHOLD = 0.001  # author choice, no ACMG/AMP precedent at this cutoff

# Common variants are less likely to be truly pathogenic, so their rank is
# pushed toward "less significant" — more at the common tier, less at the
# uncommon one. ACMG/AMP's BA1/BS1 are evidence codes, not point values, so
# none of these three sizes has an external citation: they are author
# choices, sized only so a common variant is downgraded more than a
# moderately common one, which is downgraded more than an uncommon one, and
# so that no single downgrade crosses a full significance tier on its own
# (see MAX_ADJUSTED_RANK).
COMMON_AF_PENALTY = 3.0  # author choice, no external precedent
MODERATELY_COMMON_AF_PENALTY = 1.5  # author choice, no external precedent
UNCOMMON_AF_PENALTY = 0.5  # author choice, no external precedent

# Keeps a frequency-adjusted rank below the "benign" tier boundary at 10, no
# matter how common the variant is. Author choice, not an external constant.
MAX_ADJUSTED_RANK = 9.9

# ClinVar's review-status star system (0-4 stars; see
# https://www.ncbi.nlm.nih.gov/clinvar/docs/review_status/) rates *review
# quality*, not pathogenicity, so it should only ever nudge the rank within
# its own significance tier, never move a variant into a different one.
# Significance tiers in SIGNIFICANCE_RANKS are at least 1 apart, and stars
# run 0-4, so 0.1 per star caps the maximum shift at 4 * 0.1 = 0.4 — safely
# under 1. The weight itself is an author choice, sized to satisfy that
# constraint; ClinVar's stars are the citation for the concept, not the value.
REVIEW_STAR_WEIGHT = 0.1

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
    review_stars: int = 0


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
class GnomADEntry:
    """gnomAD population frequency entry."""
    rsid: str
    allele_frequency: Optional[float] = None
    af_popmax: Optional[float] = None
    ac: Optional[int] = None
    an: Optional[int] = None
    nhomalt: Optional[int] = None


@dataclass
class VariantResult:
    """Result of variant analysis."""
    rsid: str
    chromosome: Optional[str] = None
    position: Optional[int] = None
    genotype: Optional[str] = None
    clinvar_entries: List[ClinVarEntry] = field(default_factory=list)
    gwas_entries: List[GWASEntry] = field(default_factory=list)
    gnomad_entry: Optional[GnomADEntry] = None
    category: str = VariantCategory.UNKNOWN.value
    significance_rank: float = 999


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

        # "Conflicting classifications of pathogenicity" contains "pathogenic"
        # but is not a pathogenic call, so keep it out of health conditions. It
        # has no category of its own, so it falls through to uncategorized, the
        # same place an uncertain-significance variant already lands.
        if "conflicting" in sig:
            return VariantCategory.UNKNOWN.value

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

    # "Conflicting classifications of pathogenicity" is the wording the current
    # ClinVar dump uses, and it contains the substring "pathogenic", so the
    # generic substring pass below would rank it as a pathogenic call. It is not
    # one, so catch it first.
    if "conflicting" in sig_lower:
        return SIGNIFICANCE_RANKS["conflicting interpretations"]

    # Substring matches
    for key, rank in SIGNIFICANCE_RANKS.items():
        if key in sig_lower:
            return rank

    return 999


def _calculate_frequency_adjustment(
    base_rank: float,
    gnomad_entry: Optional[GnomADEntry],
) -> float:
    """Adjust significance rank based on gnomAD allele frequency.

    Common variants are less likely to be truly pathogenic, so we increase
    their rank (making them less significant). Rare variants keep their
    original rank. See the COMMON_AF_THRESHOLD/_PENALTY family above for
    which parts of this are cited to ACMG/AMP and which are author choices.

    The adjustment is bounded so it never crosses major tier boundaries
    completely — a pathogenic variant with high AF will be downgraded but
    still noted as unusual.

    Args:
        base_rank: The original significance rank (lower = more significant)
        gnomad_entry: gnomAD frequency data, or None

    Returns:
        Adjusted rank as float (higher = less significant)
    """
    if gnomad_entry is None or gnomad_entry.allele_frequency is None:
        return base_rank

    af = gnomad_entry.allele_frequency

    # Determine adjustment based on frequency tiers
    if af > COMMON_AF_THRESHOLD:
        adjustment = COMMON_AF_PENALTY
    elif af > MODERATELY_COMMON_AF_THRESHOLD:
        adjustment = MODERATELY_COMMON_AF_PENALTY
    elif af > UNCOMMON_AF_THRESHOLD:
        adjustment = UNCOMMON_AF_PENALTY
    else:
        # Rare — no adjustment needed
        return base_rank

    return min(base_rank + adjustment, MAX_ADJUSTED_RANK)


def analyze_variants(
    variants: List[Any],
    db: AllelioDB,
    include_benign: bool = False
) -> List[VariantResult]:
    """Analyze variants against reference databases and rank them for triage.

    significance_rank is a prioritization heuristic for presentation order —
    lower means "look at this one first" — built from ClinVar's categorical
    significance, review-status quality, and gnomAD population frequency. It
    is not a clinical or diagnostic score, has not been validated as one, and
    must never be reported as one.

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
            review_status = cv_data.get("review_status")
            clinvar_entry = ClinVarEntry(
                rsid=cv_data.get("rsid"),
                gene=cv_data.get("gene"),
                clinical_significance=cv_data.get("clinical_significance"),
                conditions=cv_data.get("conditions"),
                review_status=review_status,
                review_stars=_get_review_stars(review_status),
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
        
        # Get significance rank from ClinVar, weighted by review quality
        sig_rank = 999.0
        if clinvar_entry and clinvar_entry.clinical_significance:
            base_rank = _get_significance_rank(clinvar_entry.clinical_significance)
            # Weight by review stars: higher stars lower the rank (more significant)
            # Max adjustment is 0.4 (4 stars * REVIEW_STAR_WEIGHT), so ranks never cross tiers
            sig_rank = base_rank - (clinvar_entry.review_stars * REVIEW_STAR_WEIGHT)
        elif gwas_entries:
            # For GWAS-only variants, use a default rank
            sig_rank = float(SIGNIFICANCE_RANKS.get("association", 4))
        
        # Get variant metadata
        original_variant = rsid_to_variant.get(rsid)
        chromosome = getattr(original_variant, 'chromosome', None)
        position = getattr(original_variant, 'position', None)
        genotype = getattr(original_variant, 'genotype', None)

        # Create gnomAD entry if data available
        gnomad_entry = None
        if data.get("gnomad"):
            gn = data["gnomad"]
            gnomad_entry = GnomADEntry(
                rsid=gn.get("rsid", rsid),
                allele_frequency=gn.get("allele_frequency"),
                af_popmax=gn.get("af_popmax"),
                ac=gn.get("ac"),
                an=gn.get("an"),
                nhomalt=gn.get("nhomalt"),
            )

        # Adjust significance rank based on population frequency
        adjusted_rank = _calculate_frequency_adjustment(sig_rank, gnomad_entry)

        # Skip benign variants unless requested
        if not include_benign and adjusted_rank >= 8:
            continue

        # Create result
        result = VariantResult(
            rsid=rsid,
            chromosome=chromosome,
            position=position,
            genotype=genotype,
            clinvar_entries=[clinvar_entry] if clinvar_entry else [],
            gwas_entries=gwas_entries,
            gnomad_entry=gnomad_entry,
            category=category,
            significance_rank=adjusted_rank,
        )

        results.append(result)
    
    # Sort by significance rank (lower = more significant)
    results.sort(key=lambda x: x.significance_rank)
    
    return results
