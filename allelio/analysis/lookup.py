"""Variant lookup and analysis engine."""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

from allelio.database.store import AllelioDB
from allelio.database.clinpgx import level_rank as pgx_level_rank
from allelio.analysis.zygosity import Zygosity, ZygosityCall, call_zygosity, genotype_alleles, call_vcf_zygosity
from allelio.parsers.base import VCFEvidence


# ClinVar review status to star rating mapping (0-4 stars)
# See: https://www.ncbi.nlm.nih.gov/clinvar/docs/review_status/
REVIEW_STATUS_STARS = {
    "practice guideline": 4,
    "reviewed by expert panel": 3,
    "criteria provided, multiple submitters, no conflicts": 2,
    "criteria provided, multiple submitters": 2,
    "criteria provided, conflicting interpretations": 1,
    # ClinVar renamed "interpretations" to "classifications" in 2024.
    "criteria provided, conflicting classifications": 1,
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
    # ClinVar's "drug response" is an actionable classification (dosing,
    # efficacy, toxicity), ranked with risk factors. Author choice.
    "drug response": 3,
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
    # One copy of a pathogenic allele in a gene ClinGen curates only for
    # recessive conditions (or one copy on a diploid X for an X-linked one).
    CARRIER_STATUS = "Carrier Status"
    BENIGN = "Benign"
    UNKNOWN = "Unknown"


# A heterozygous carrier of a recessive pathogenic allele is a real finding
# (reproductive planning) but not the affected genotype, so it is ordered
# below dominant and homozygous pathogenic findings. One full tier; author
# choice, no external precedent for the size.
CARRIER_RANK_SHIFT = 1.0

# ClinPGx level of evidence → presentation rank. 1A/1B (guideline- or
# label-backed, or strongly replicated) rank with risk factors and ClinVar's
# drug response; 2A/2B a tier below; 3 and 4 with conflicting/uncertain
# evidence. Author choices, sized to the existing tiers; ClinPGx's levels are
# the citation for the ordering, not the numbers.
PGX_LEVEL_RANKS = {"1A": 3.0, "1B": 3.0, "2A": 4.0, "2B": 4.0, "3": 6.0, "4": 7.0}

# Annotations below this level are not reported by default: level 3 is
# "low evidence" (a single study, or conflicting ones) and there are
# thousands of them, so a real file would drown in single-study drug notes.
PGX_DEFAULT_MIN_LEVEL = "2B"

# ClinGen classifications that count as an established gene-disease link when
# deciding the mode of inheritance. Limited / Disputed / Refuted / "No Known
# Disease Relationship" do not decide it.
CLINGEN_ESTABLISHED = ("Definitive", "Strong", "Moderate")


@dataclass
class ClinVarEntry:
    """ClinVar variant entry, one classified allele at one rsID."""
    rsid: str
    gene: Optional[str] = None
    clinical_significance: Optional[str] = None
    conditions: Optional[str] = None
    review_status: Optional[str] = None
    review_stars: int = 0
    ref_allele: Optional[str] = None
    alt_allele: Optional[str] = None


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
    risk_allele: Optional[str] = None


@dataclass
class ClinGenEntry:
    """One ClinGen gene-disease validity curation."""
    gene: str
    disease: Optional[str] = None
    moi: Optional[str] = None
    classification: Optional[str] = None
    report_url: Optional[str] = None


@dataclass
class PGxEntry:
    """One ClinPGx clinical annotation, with the text for this genotype."""
    rsid: str
    annotation_id: str
    gene: Optional[str] = None
    level: Optional[str] = None
    phenotype_category: Optional[str] = None
    drugs: Optional[str] = None
    phenotypes: Optional[str] = None
    url: Optional[str] = None
    genotype: Optional[str] = None
    annotation_text: Optional[str] = None
    allele_function: Optional[str] = None
    strand_flipped: bool = False


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
    # How many copies of the annotated allele the user carries, the
    # difference between a carrier, an affected genotype, and an entry that
    # does not apply to this person at all. See allelio/analysis/zygosity.py.
    zygosity: str = Zygosity.UNKNOWN.value
    alt_copies: Optional[int] = None
    matched_allele: Optional[str] = None
    strand_flipped: bool = False
    zygosity_note: Optional[str] = None
    allele_role: str = "alternate"
    # ClinGen's curations for the gene, and what they say about inheritance:
    # "autosomal recessive", "autosomal dominant", "X-linked", "mixed
    # (dominant and recessive conditions)", or "not curated".
    clingen_entries: List[ClinGenEntry] = field(default_factory=list)
    inheritance: str = "not curated"
    inheritance_note: Optional[str] = None
    # ClinPGx annotations whose genotype row matches this person's genotype,
    # best level of evidence first.
    pgx_entries: List[PGxEntry] = field(default_factory=list)

    @property
    def pgx_level(self) -> Optional[str]:
        """Best ClinPGx level of evidence among the matched annotations."""
        return self.pgx_entries[0].level if self.pgx_entries else None

    def describe_zygosity(self) -> str:
        """Report phrase, e.g. ``heterozygous (1 copy of the A allele)``."""
        return ZygosityCall(
            Zygosity(self.zygosity), self.alt_copies, self.matched_allele,
            self.strand_flipped, self.zygosity_note, self.allele_role,
        ).describe()


class AnalysisResults(list):
    """A list of VariantResult that also carries the ``AnalysisStats``.

    ``analyze_variants`` returns one of these so callers keep getting a plain
    list while the counts of what was set aside travel with it (``.stats``).
    """

    def __init__(self, results=(), stats: Optional["AnalysisStats"] = None):
        super().__init__(results)
        self.stats = stats if stats is not None else AnalysisStats()


@dataclass
class AnalysisStats:
    """What happened to the annotated sites that are not in the results.

    Attributes:
        annotated_sites: rsIDs in the file with at least one ClinVar/GWAS row.
        reference_genotype_sites: annotated sites where the user carries no
            copy of any annotated allele. These are not findings and are left
            out; the count is reported so the omission is visible.
        zygosity_unknown_sites: sites reported without a zygosity call,
            because the source does not give the allele or the genotype does
            not match it on either strand.
        benign_sites: sites left out because every match was benign
            (unless include_benign).
    """
    annotated_sites: int = 0
    reference_genotype_sites: int = 0
    zygosity_unknown_sites: int = 0
    benign_sites: int = 0


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

        # ClinVar's own pharmacogenomic classification
        if "drug response" in sig:
            return VariantCategory.PHARMACOGENOMICS.value

        # Check for risk factors
        if any(x in sig for x in ["risk factor", "risk_factor", "association"]):
            return VariantCategory.RISK_FACTORS.value

        # Benign / likely benign
        if "likely benign" in sig or "benign" in sig:
            return VariantCategory.BENIGN.value
    
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


def _clinvar_entry(cv_data: Dict[str, Any]) -> ClinVarEntry:
    review_status = cv_data.get("review_status")
    return ClinVarEntry(
        rsid=cv_data.get("rsid"),
        gene=cv_data.get("gene"),
        clinical_significance=cv_data.get("clinical_significance"),
        conditions=cv_data.get("conditions"),
        review_status=review_status,
        review_stars=_get_review_stars(review_status),
        ref_allele=cv_data.get("ref_allele") or None,
        alt_allele=cv_data.get("alt_allele") or None,
    )


def _rank_clinvar(entry: ClinVarEntry) -> float:
    """Significance rank for one ClinVar row, weighted by review quality."""
    if not entry.clinical_significance:
        return 999.0
    base_rank = _get_significance_rank(entry.clinical_significance)
    # Weight by review stars: higher stars lower the rank (more significant)
    # Max adjustment is 0.4 (4 stars * REVIEW_STAR_WEIGHT), so ranks never cross tiers
    return base_rank - (entry.review_stars * REVIEW_STAR_WEIGHT)


def _select_clinvar_rows(
    genotype: Optional[str], rows: List[Dict[str, Any]],
    vcf_evidence: Optional[VCFEvidence] = None,
) -> Tuple[List[ClinVarEntry], Optional[ZygosityCall], bool]:
    """Pick the ClinVar rows that apply to this genotype.

    ClinVar can hold several rows for one rsID, one per alternate allele. Only
    the rows whose allele the user carries are findings for that user; rows
    whose alleles ClinVar does not record cannot be checked and are kept with
    an unknown zygosity, as every row was before alleles were stored.

    Returns:
        (entries, call, is_reference), the applicable entries ordered most
        significant first, the zygosity call for the first of them, and
        True when the user carries no copy of any annotated allele (nothing
        applies; the site is a reference genotype, not a finding).
    """
    carried: List[Tuple[ClinVarEntry, ZygosityCall]] = []
    unknown: List[Tuple[ClinVarEntry, ZygosityCall]] = []
    absent: List[Tuple[ClinVarEntry, ZygosityCall]] = []
    entries = [_clinvar_entry(cv) for cv in rows]
    # A row whose ref equals its alt is a haplotype-level record that names no
    # allele of its own. Where the same rsID also has allele-specific rows,
    # those are the ones to judge by; the degenerate row is dropped so it
    # cannot resurface as a "zygosity unknown" finding beside them.
    if any(e.ref_allele and e.alt_allele and e.ref_allele != e.alt_allele for e in entries):
        entries = [e for e in entries if not (e.ref_allele and e.ref_allele == e.alt_allele)]
    for entry in entries:
        call = (call_vcf_zygosity(vcf_evidence, entry.ref_allele, entry.alt_allele)
                if vcf_evidence is not None
                else call_zygosity(genotype, entry.ref_allele, entry.alt_allele))
        if call.alt_copies is None:
            unknown.append((entry, call))
        elif call.alt_copies > 0:
            carried.append((entry, call))
        else:
            absent.append((entry, call))

    if carried:
        carried.sort(key=lambda ec: _rank_clinvar(ec[0]))
        return [e for e, _ in carried], carried[0][1], False
    if unknown:
        unknown.sort(key=lambda ec: _rank_clinvar(ec[0]))
        return [e for e, _ in unknown], unknown[0][1], False
    if absent:
        # Every allele ClinVar knows about was checked and none is carried.
        # The entries come back so a caller that asked to see reference
        # sites can show what was set aside; the flag says they do not apply.
        absent.sort(key=lambda ec: _rank_clinvar(ec[0]))
        return [e for e, _ in absent], absent[0][1], True
    return [], None, False


_COMPLEMENT = {"A": "T", "T": "A", "C": "G", "G": "C"}


def _gwas_call(
    genotype: Optional[str],
    entries: List[GWASEntry],
    site_alleles: Optional[set] = None,
) -> Optional[ZygosityCall]:
    """Zygosity against the GWAS risk alleles, if the catalogue names any.

    The GWAS Catalog gives only the risk allele (no reference), and studies do
    not always report it on the forward strand. Where ClinVar has told us the
    site's forward-strand alleles (``site_alleles``), a risk allele that is
    not one of them but whose complement is gets complemented, and the call
    is flagged as read on the opposite strand; at an A/T or C/G site that
    inference is impossible and the mismatch stays unknown.

    Every entry with a risk allele is considered. The result is the first
    carried allele (most useful), else unknown if any entry could not be
    judged, else "no copies" only when every named allele was checked and
    none is carried. None if no entry names an allele.
    """
    site_alleles = {a for a in (site_alleles or set()) if a}
    ambiguous = site_alleles in ({"A", "T"}, {"C", "G"})
    unknown: Optional[ZygosityCall] = None
    absent: Optional[ZygosityCall] = None
    seen = set()
    for e in entries:
        allele = (e.risk_allele or "").upper()
        if not allele or allele in seen:
            continue
        seen.add(allele)
        flipped = False
        if (
            site_alleles and allele not in site_alleles and not ambiguous
            and _COMPLEMENT.get(allele) in site_alleles
        ):
            allele = _COMPLEMENT[allele]
            flipped = True
        call = call_zygosity(genotype, None, allele)
        if flipped and call.alt_copies is not None:
            call = ZygosityCall(
                call.zygosity, call.alt_copies, e.risk_allele.upper(),
                strand_flipped=True, allele_role="risk",
            )
        if call.alt_copies:
            return call
        if call.alt_copies is None:
            unknown = unknown or call
        else:
            absent = absent or call
    if unknown is not None:
        return unknown
    return absent


_PGX_COMPLEMENT = {"A": "T", "T": "A", "C": "G", "G": "C"}


def _match_pgx(
    genotype: Optional[str],
    rows: List[Dict[str, Any]],
    site_alleles: Optional[set] = None,
    min_level: str = PGX_DEFAULT_MIN_LEVEL,
) -> List[PGxEntry]:
    """The ClinPGx rows whose genotype is this person's genotype.

    ClinPGx writes genotypes as two forward-strand letters ("CT"); order does
    not matter. If the person's letters are not among those the annotation
    uses on either allele but their complements are, and the site is not
    A/T or C/G (where a flip is undetectable), the complement is used and
    the entry flagged. Rows below ``min_level`` are dropped. Best level first.
    """
    alleles = genotype_alleles(genotype)
    if len(alleles) != 2 or not rows:
        return []
    key = "".join(sorted(alleles))
    max_rank = pgx_level_rank(min_level)
    usable = [r for r in rows if pgx_level_rank(r.get("level")) <= max_rank]
    if not usable:
        return []
    by_genotype: Dict[str, List[Dict[str, Any]]] = {}
    letters = set()
    for r in usable:
        g = (r.get("genotype") or "").upper()
        if len(g) == 2 and g.isalpha():
            by_genotype.setdefault("".join(sorted(g)), []).append(r)
            letters.update(g)
    flipped = False
    matched = by_genotype.get(key)
    if matched is None:
        site = {a for a in (site_alleles or set()) if a} or letters
        ambiguous = site in ({"A", "T"}, {"C", "G"})
        comp = "".join(sorted(_PGX_COMPLEMENT.get(a, a) for a in alleles))
        if not ambiguous and comp in by_genotype and not any(a in letters for a in alleles):
            matched, flipped = by_genotype[comp], True
    if not matched:
        return []
    entries = [
        PGxEntry(
            rsid=r.get("rsid"), annotation_id=r.get("annotation_id"), gene=r.get("gene"),
            level=r.get("level"), phenotype_category=r.get("phenotype_category"),
            drugs=r.get("drugs"), phenotypes=r.get("phenotypes"), url=r.get("url"),
            genotype=r.get("genotype"), annotation_text=r.get("annotation_text"),
            allele_function=r.get("allele_function"), strand_flipped=flipped,
        )
        for r in matched
    ]
    entries.sort(key=lambda e: (pgx_level_rank(e.level), e.drugs or ""))
    return entries


def _inheritance(entries: List[ClinGenEntry]) -> Tuple[str, Optional[str]]:
    """Summarise ClinGen's curations for a gene as one inheritance phrase.

    Only established curations (see CLINGEN_ESTABLISHED) decide it. A gene
    curated for both dominant and recessive conditions reads "mixed": with
    one copy, whether that is carrier status depends on which condition the
    allele causes, which gene-level curation cannot say.

    Returns:
        (inheritance, note), e.g. ("autosomal recessive", "ClinGen:
        hemochromatosis type 1 (Definitive)").
    """
    from allelio.database.clingen import MOI_LABELS

    established = [e for e in entries if (e.classification or "") in CLINGEN_ESTABLISHED]
    if not entries:
        return "not curated", None
    if not established:
        return "not established", (
            "ClinGen lists no established gene-disease relationship for this gene ("
            + "; ".join(f"{e.disease}: {e.classification}" for e in entries[:3]) + ")"
        )
    mois = {e.moi for e in established if e.moi}
    note = "ClinGen: " + "; ".join(
        f"{e.disease} ({MOI_LABELS.get(e.moi, e.moi or '?')}, {e.classification})" for e in established[:4]
    )
    if mois == {"AR"}:
        return "autosomal recessive", note
    if mois == {"AD"}:
        return "autosomal dominant", note
    if mois == {"XL"}:
        return "X-linked", note
    if mois == {"SD"}:
        return "semidominant", note
    if mois == {"MT"}:
        return "mitochondrial", note
    if "AR" in mois and ("AD" in mois or "SD" in mois or "XL" in mois):
        return "mixed (dominant and recessive conditions)", note
    return ", ".join(sorted(MOI_LABELS.get(m, m) for m in mois)) or "undetermined", note


def _carrier(inheritance: str, call: ZygosityCall, genotype: Optional[str]) -> bool:
    """One copy of the allele where inheritance says one copy is a carrier."""
    if call.alt_copies != 1:
        return False
    if inheritance == "autosomal recessive":
        return True
    if inheritance == "X-linked":
        # A single-letter genotype is hemizygous (one X): affected, not carrier.
        return len(genotype or "") == 2
    return False


def analyze_variants_with_stats(
    variants: List[Any],
    db: AllelioDB,
    include_benign: bool = False,
    include_reference: bool = False,
    frequency_adjustment: bool = True,
    pgx_min_level: str = PGX_DEFAULT_MIN_LEVEL,
) -> Tuple[List[VariantResult], AnalysisStats]:
    """Like ``analyze_variants`` but also returns what was left out and why.

    Args:
        variants: List of Variant objects with rsid attribute
        db: AllelioDB database instance
        include_benign: Whether to include benign variants in results
        include_reference: Whether to include annotated sites where the user
            carries no copy of the annotated allele (never findings; off by
            default and counted in the stats instead)
        frequency_adjustment: Apply the gnomAD allele-frequency adjustment to
            the rank (the default). Off, the rank is ClinVar significance
            weighted by review stars only; used by scripts/ablation_frequency.py
            to show what the adjustment changes.

    Returns:
        (results sorted by significance rank, AnalysisStats)
    """
    stats = AnalysisStats()
    if not variants:
        return [], stats

    # Extract rsIDs from variant objects
    rsids = [getattr(v, 'rsid', str(v)) for v in variants]
    rsids = [r for r in rsids if r]  # Filter empty rsids

    if not rsids:
        return [], stats

    # Create mapping of rsid to original variant for metadata
    rsid_to_variant = {
        getattr(v, 'rsid', str(v)): v for v in variants
    }

    # Batch lookup from database
    lookup_results = db.lookup_rsids_batch(rsids)

    # ClinGen curations for every gene ClinVar names, in one query
    genes = {
        cv.get("gene") for data in lookup_results.values() for cv in data["clinvar"] if cv.get("gene")
    }
    genes = {g for name in genes for g in name.split(";") if g}
    clingen_by_gene = {}
    try:
        clingen_by_gene = db.lookup_clingen_genes(sorted(genes))
    except Exception:
        clingen_by_gene = {}

    # ClinPGx rows for every rsID (a site can be PGx-only)
    try:
        pgx_by_rsid = db.lookup_clinpgx(rsids)
    except Exception:
        pgx_by_rsid = {}

    # Build results
    results = []

    for rsid, data in lookup_results.items():
        pgx_rows = pgx_by_rsid.get(rsid) or []
        if not data["clinvar"] and not data["gwas"] and not pgx_rows:
            continue
        stats.annotated_sites += 1

        # Get variant metadata
        original_variant = rsid_to_variant.get(rsid)
        chromosome = getattr(original_variant, 'chromosome', None)
        position = getattr(original_variant, 'position', None)
        genotype = getattr(original_variant, 'genotype', None)

        vcf_evidence = getattr(original_variant, 'vcf_evidence', None)
        # Do not let non-SNP sequences reach legacy SNP/GWAS/PGx matching as
        # concatenated bases. Their complete alleles remain in source evidence.
        if vcf_evidence is not None and any(
            a not in {"A", "C", "G", "T"}
            for a in (vcf_evidence.reference,) + vcf_evidence.alternates
        ):
            genotype = "--"

        # ClinVar rows that apply to this genotype (allele-aware)
        clinvar_entries, call, is_reference = _select_clinvar_rows(
            genotype, data["clinvar"], vcf_evidence
        )
        clinvar_entry = clinvar_entries[0] if clinvar_entries else None

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
                pubmed_id=gw_data.get("pubmed_id"),
                risk_allele=gw_data.get("risk_allele"),
            ))

        # A site where the user carries none of ClinVar's annotated alleles is
        # not a ClinVar finding for them. If GWAS rows remain, judge those on
        # their own risk allele; otherwise the site is a reference genotype.
        gwas_reference = False
        if gwas_entries and (is_reference or call is None):
            site_alleles = {
                a for cv in data["clinvar"] for a in (cv.get("ref_allele"), cv.get("alt_allele")) if a
            }
            gcall = _gwas_call(genotype, gwas_entries, site_alleles)
            if gcall is not None and gcall.alt_copies == 0:
                gwas_reference = True
            elif is_reference or call is None:
                call = gcall if gcall is not None else call

        # ClinPGx: the annotation rows written for this person's genotype
        site_alleles_pgx = {
            a for cv in data["clinvar"] for a in (cv.get("ref_allele"), cv.get("alt_allele")) if a
        }
        pgx_entries = _match_pgx(genotype, pgx_rows, site_alleles_pgx, pgx_min_level)

        site_is_reference = (
            (is_reference or not clinvar_entries) and (gwas_reference or not gwas_entries)
            and not pgx_entries
        )
        if site_is_reference:
            stats.reference_genotype_sites += 1
            if not include_reference:
                continue
            if call is None:
                call = ZygosityCall(Zygosity.HOMOZYGOUS_REFERENCE, 0)
        elif is_reference:
            # ClinVar rows do not apply; only the GWAS association remains.
            clinvar_entries = []
        elif gwas_reference:
            gwas_entries = []
        clinvar_entry = clinvar_entries[0] if clinvar_entries else None

        # Determine category
        category = _determine_category(clinvar_entry, gwas_entries)

        # Get significance rank from ClinVar, weighted by review quality
        sig_rank = 999.0
        if clinvar_entry and clinvar_entry.clinical_significance:
            sig_rank = _rank_clinvar(clinvar_entry)
        elif gwas_entries:
            # For GWAS-only variants, use a default rank
            sig_rank = float(SIGNIFICANCE_RANKS.get("association", 4))

        # A ClinPGx annotation for this genotype: rank by its best level, and
        # file the site under Pharmacogenomics unless ClinVar already calls
        # it a health condition or risk factor (those stay where they are;
        # the drug notes travel with the card).
        if pgx_entries:
            pgx_rank = PGX_LEVEL_RANKS.get(pgx_entries[0].level or "", 7.0)
            sig_rank = min(sig_rank, pgx_rank)
            if category not in (VariantCategory.HEALTH_CONDITIONS.value, VariantCategory.RISK_FACTORS.value):
                category = VariantCategory.PHARMACOGENOMICS.value

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

        # Adjust significance rank based on population frequency. Not for
        # pharmacogenomic findings: the adjustment encodes "a common allele is
        # unlikely to be pathogenic", and a drug-response allele is not a
        # pathogenicity claim, most are common by nature (VKORC1 -1639G>A is
        # carried by a third of Europeans) and no less actionable for it.
        pharmacogenomic = category == VariantCategory.PHARMACOGENOMICS.value
        adjusted_rank = (
            _calculate_frequency_adjustment(sig_rank, gnomad_entry)
            if frequency_adjustment and not pharmacogenomic else sig_rank
        )

        # Skip benign variants unless requested
        if not include_benign and adjusted_rank >= 8:
            stats.benign_sites += 1
            continue

        if call is None:
            call = ZygosityCall(Zygosity.UNKNOWN, None, note="annotated allele not recorded")
        if call.alt_copies is None and call.zygosity != Zygosity.NO_CALL:
            stats.zygosity_unknown_sites += 1

        # Inheritance from ClinGen, and the carrier rule: one copy of a
        # pathogenic allele in a recessive-only gene is carrier status, ordered
        # a tier below the affected genotype.
        clingen_entries: List[ClinGenEntry] = []
        inheritance, inheritance_note = "not curated", None
        if clinvar_entry and clinvar_entry.gene:
            # ClinVar can list several overlapping genes ("MC1R;TUBB3"); the
            # first is the one the record is about, and a curation for a
            # neighbouring gene says nothing about this allele.
            for g in clinvar_entry.gene.split(";")[:1]:
                for row in clingen_by_gene.get(g, []):
                    clingen_entries.append(ClinGenEntry(
                        gene=row.get("gene"), disease=row.get("disease"), moi=row.get("moi"),
                        classification=row.get("classification"), report_url=row.get("report_url"),
                    ))
            inheritance, inheritance_note = _inheritance(clingen_entries)
            if category == VariantCategory.HEALTH_CONDITIONS.value and _carrier(inheritance, call, genotype):
                category = VariantCategory.CARRIER_STATUS.value
                adjusted_rank = min(adjusted_rank + CARRIER_RANK_SHIFT, MAX_ADJUSTED_RANK)

        # Create result
        result = VariantResult(
            rsid=rsid,
            chromosome=chromosome,
            position=position,
            genotype=genotype,
            clinvar_entries=clinvar_entries,
            gwas_entries=gwas_entries,
            gnomad_entry=gnomad_entry,
            category=category,
            significance_rank=adjusted_rank,
            zygosity=call.zygosity.value,
            alt_copies=call.alt_copies,
            matched_allele=call.allele,
            strand_flipped=call.strand_flipped,
            zygosity_note=call.note,
            allele_role=call.allele_role,
            clingen_entries=clingen_entries,
            inheritance=inheritance,
            inheritance_note=inheritance_note,
            pgx_entries=pgx_entries,
        )

        results.append(result)

    # Sort by significance rank (lower = more significant); ties by rsID so
    # the order is the same on every run and every machine.
    results.sort(key=lambda x: (x.significance_rank, x.rsid))

    return results, stats


def analyze_variants(
    variants: List[Any],
    db: AllelioDB,
    include_benign: bool = False,
    include_reference: bool = False,
) -> List[VariantResult]:
    """Analyze variants against reference databases and rank them for triage.

    significance_rank is a prioritization heuristic for presentation order,
    lower means "look at this one first", built from ClinVar's categorical
    significance, review-status quality, and gnomAD population frequency. It
    is not a clinical or diagnostic score, has not been validated as one, and
    must never be reported as one.

    Each result also carries a zygosity call: how many copies of the
    annotated allele the user has. Sites where the user carries no copy of
    any annotated allele are not findings and are left out (see
    ``analyze_variants_with_stats`` for the counts).

    Args:
        variants: List of Variant objects with rsid attribute
        db: AllelioDB database instance
        include_benign: Whether to include benign variants in results
        include_reference: Whether to include reference-genotype sites

    Returns:
        ``AnalysisResults``, a list of VariantResult sorted by significance
        rank, with the ``AnalysisStats`` on its ``.stats`` attribute
    """
    results, stats = analyze_variants_with_stats(variants, db, include_benign, include_reference)
    return AnalysisResults(results, stats)
