"""Variant lookup and analysis engine."""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

from allelio.database.store import AllelioDB
from allelio.database.clinpgx import level_rank as pgx_level_rank
from allelio.analysis.zygosity import Zygosity, ZygosityCall, call_zygosity, genotype_alleles, call_vcf_zygosity
from allelio.parsers.base import VCFEvidence
from allelio.analysis.identity import vcf_identity_reason
from allelio.analysis.frequency import (
    AlleleAnchor, MATCHED as FREQUENCY_MATCHED, UNVERIFIED as FREQUENCY_UNVERIFIED,
    frequency_identity, valid_frequency,
)
from allelio.analysis.identity import declared_build
from allelio.analysis import trace as tr
from allelio.analysis.trace import MatchTrace
from allelio.analysis.quality import vcf_filter_reason
from allelio.analysis.inheritance import (
    ClinGenEntry, InheritanceResolution, is_carrier, resolve_inheritance,
)


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
# These are display-priority heuristics, not ACMG/AMP classification rules.
# BS1 depends on the disorder; 1% is not a universal BS1 cutoff. Frequency
# alone establishes neither benignity nor pathogenicity.
COMMON_AF_THRESHOLD = 0.05
MODERATELY_COMMON_AF_THRESHOLD = 0.01
UNCOMMON_AF_THRESHOLD = 0.001
COMMON_AF_PENALTY = 3.0
MODERATELY_COMMON_AF_PENALTY = 1.5
UNCOMMON_AF_PENALTY = 0.5

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
    # One copy of a pathogenic allele whose ClinVar condition ClinGen curates
    # as recessive (or X-linked, on a diploid genotype). Decided per
    # assertion by MONDO identifier; see allelio/analysis/inheritance.py.
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
    assembly: Optional[str] = None
    chromosome: Optional[str] = None
    position_vcf: Optional[int] = None
    allele_id: Optional[str] = None
    variation_id: Optional[str] = None
    hgnc_id: Optional[str] = None
    # ClinVar PhenotypeIDS, parallel to ``conditions``; None when the database
    # predates the column. See allelio/analysis/inheritance.py.
    condition_ids: Optional[str] = None
    # How this assertion's own conditions are inherited, per ClinGen. Set for
    # every applicable assertion once the result's gene is known.
    inheritance: Optional[InheritanceResolution] = None
    # What ``clinical_significance`` is: "germline" (the aggregate germline
    # classification of a post-2024 file), "unsplit" (an older file that
    # mixed germline and somatic in one column), or "unknown" (legacy
    # database). Never assumed. See docs/clinvar-fields.md.
    classification_type: str = "unknown"
    # Context ClinVar gives for reading the classification, verbatim; None
    # is unknown or not asserted, never "germline by default".
    origin: Optional[str] = None
    origin_simple: Optional[str] = None
    rcv_accessions: Optional[str] = None
    number_submitters: Optional[int] = None
    variant_type: Optional[str] = None
    name: Optional[str] = None
    somatic_clinical_impact: Optional[str] = None
    somatic_review_status: Optional[str] = None
    somatic_last_evaluated: Optional[str] = None
    oncogenicity: Optional[str] = None
    oncogenicity_review_status: Optional[str] = None
    oncogenicity_last_evaluated: Optional[str] = None
    # Three things a reader must not conflate, kept apart: the source
    # classification above, whether this person carries the allele it is
    # about (``allele_match``: "carried", "unknown", "absent", with the copy
    # count or the reason), and Allelio's own display rank for the row.
    allele_match: str = "unknown"
    allele_match_note: Optional[str] = None
    display_rank: Optional[float] = None

    @property
    def rcv_list(self) -> List[str]:
        """The per-condition record accessions this row aggregates."""
        return [a for a in (self.rcv_accessions or "").split("|") if a]

    def context_phrases(self) -> List[str]:
        """Short phrases saying what kind of classification this is and its context.

        The same phrases feed the HTML report, the web card, the AI prompt,
        the fallback text, and (as fields) the evidence JSON. Absent context
        reads as unknown; a somatic or oncogenicity assertion is named
        separately from the germline one, never folded into it.
        """
        phrases: List[str] = []
        if self.classification_type == "germline":
            phrases.append("germline classification (aggregate across the listed conditions)")
        elif self.classification_type == "unsplit":
            phrases.append("classification from a pre-2024 ClinVar file that mixed germline and somatic assertions")
        else:
            phrases.append("classification type unknown (database predates context columns; run allelio update)")
        if self.origin_simple or self.origin:
            origin = self.origin_simple or self.origin
            detail = f" ({self.origin})" if self.origin and self.origin != origin else ""
            phrases.append(f"origin: {origin}{detail}")
        elif self.classification_type != "unknown":
            phrases.append("origin: not provided")
        if self.somatic_clinical_impact:
            status = f"; {self.somatic_review_status}" if self.somatic_review_status else ""
            date = f"; {self.somatic_last_evaluated}" if self.somatic_last_evaluated else ""
            phrases.append(f"somatic clinical impact: {self.somatic_clinical_impact}{status}{date}")
        if self.oncogenicity:
            status = f"; {self.oncogenicity_review_status}" if self.oncogenicity_review_status else ""
            date = f"; {self.oncogenicity_last_evaluated}" if self.oncogenicity_last_evaluated else ""
            phrases.append(f"oncogenicity: {self.oncogenicity}{status}{date}")
        rcvs = self.rcv_list
        if rcvs or self.number_submitters is not None:
            parts = []
            if rcvs:
                parts.append(f"{len(rcvs)} condition record{'s' if len(rcvs) != 1 else ''} (RCV)")
            if self.number_submitters is not None:
                parts.append(f"{self.number_submitters} submitter{'s' if self.number_submitters != 1 else ''}")
            phrases.append("aggregates " + ", ".join(parts) + "; per-condition classifications are not in this source file")
        return phrases


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
    """One gnomAD frequency record, and whether it describes the matched allele.

    ``identity`` is ``matched`` only when the record's assembly, chromosome,
    position, REF and ALT agree with a checked source identity for the
    allele the person carries (see allelio/analysis/frequency.py). Every
    other value keeps the record inspectable as context without implying
    that the frequency belongs to this allele; ``identity_note`` says why.
    """
    rsid: str
    allele_frequency: Optional[float] = None
    af_popmax: Optional[float] = None
    ac: Optional[int] = None
    an: Optional[int] = None
    nhomalt: Optional[int] = None
    af_afr: Optional[float] = None
    af_eas: Optional[float] = None
    af_fin: Optional[float] = None
    af_nfe: Optional[float] = None
    af_sas: Optional[float] = None
    chromosome: Optional[str] = None
    position: Optional[int] = None
    ref_allele: Optional[str] = None
    alt_allele: Optional[str] = None
    assembly: Optional[str] = None
    source_version: Optional[str] = None
    identity: str = FREQUENCY_UNVERIFIED
    identity_note: Optional[str] = None

    @property
    def describes_matched_allele(self) -> bool:
        return self.identity == FREQUENCY_MATCHED


@dataclass
class VariantResult:
    """Result of variant analysis."""
    rsid: str
    chromosome: Optional[str] = None
    position: Optional[int] = None
    genotype: Optional[str] = None
    clinvar_entries: List[ClinVarEntry] = field(default_factory=list)
    gwas_entries: List[GWASEntry] = field(default_factory=list)
    # The frequency record for the matched allele when exactly one agrees
    # with its checked identity; otherwise the single record at the rsID,
    # flagged as context (``identity`` says why it was not applied), or
    # None. Every record at the rsID is in ``gnomad_entries``.
    gnomad_entry: Optional[GnomADEntry] = None
    gnomad_entries: List[GnomADEntry] = field(default_factory=list)
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
    # ClinGen's curations for the gene, and the inheritance of the condition
    # the primary ClinVar assertion is about: "autosomal recessive",
    # "autosomal dominant", "X-linked", or an unresolved phrase that says
    # why ("conflicting (...)", "unresolved (...)", "not curated"). The full
    # resolution, with the matched curations, the mapping that produced it,
    # and the gene-level summary kept separately, is ``inheritance_resolution``.
    clingen_entries: List[ClinGenEntry] = field(default_factory=list)
    inheritance: str = "not curated"
    inheritance_note: Optional[str] = None
    inheritance_resolution: Optional[InheritanceResolution] = None
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
        vcf_filter_failed_sites: annotated sites set aside because VCF FILTER
            or FORMAT/FT explicitly failed; not reference calls or benign findings.
        benign_sites: sites left out because every match was benign
            (unless include_benign).
    """
    annotated_sites: int = 0
    reference_genotype_sites: int = 0
    zygosity_unknown_sites: int = 0
    benign_sites: int = 0
    vcf_filter_failed_sites: int = 0
    dispositions: Dict[str, str] = field(default_factory=dict)
    duplicate_rows: int = 0
    conflicting_input_sites: int = 0
    # One decision per candidate source record considered, with its reason;
    # see allelio/analysis/trace.py. Counted separately from input rows and
    # from returned findings.
    trace: MatchTrace = field(default_factory=MatchTrace)


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
    """Apply an optional display penalty; never change source classifications.

    Valid frequencies above the configured tiers increase the numeric rank
    (lower display priority). Missing/invalid values leave it unchanged, and
    so does a record whose allele identity is not verified as the matched
    allele's: a frequency for a different allele, build, or position, or
    for no recorded allele at all, must not move the rank.
    The cap never improves a rank already at or beyond the cap.
    """
    if gnomad_entry is None or not valid_frequency(gnomad_entry.allele_frequency):
        return base_rank
    if not gnomad_entry.describes_matched_allele:
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

    return max(base_rank, min(base_rank + adjustment, MAX_ADJUSTED_RANK))


def _clinvar_entry(cv_data: Dict[str, Any]) -> ClinVarEntry:
    review_status = cv_data.get("review_status")
    return ClinVarEntry(
        rsid=cv_data.get("rsid"),
        gene=cv_data.get("gene"),
        clinical_significance=cv_data.get("clinical_significance"),
        classification_type=cv_data.get("classification_type") or "unknown",
        conditions=cv_data.get("conditions"),
        review_status=review_status,
        review_stars=_get_review_stars(review_status),
        ref_allele=cv_data.get("ref_allele") or None,
        alt_allele=cv_data.get("alt_allele") or None,
        chromosome=cv_data.get("chromosome") or None,
        allele_id=cv_data.get("allele_id") or None,
        **{key: cv_data.get(key) for key in (
            "assembly", "position_vcf", "variation_id", "hgnc_id", "condition_ids",
            "origin", "origin_simple", "rcv_accessions", "number_submitters", "variant_type", "name",
            "somatic_clinical_impact", "somatic_review_status", "somatic_last_evaluated",
            "oncogenicity", "oncogenicity_review_status", "oncogenicity_last_evaluated",
        )},
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
    chromosome: Optional[str] = None, position: Optional[int] = None,
    trace: Optional[MatchTrace] = None, rsid: Optional[str] = None,
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
        for e in entries:
            if e.ref_allele and e.ref_allele == e.alt_allele and trace is not None:
                trace.add(rsid or e.rsid, "clinvar", tr.source_identity("clinvar", e), tr.REJECTED,
                          tr.STAGE_APPLICABILITY, "haplotype_row_superseded",
                          "record names no allele of its own; allele-specific records at this site decide")
        entries = [e for e in entries if not (e.ref_allele and e.ref_allele == e.alt_allele)]
    for entry in entries:
        if vcf_evidence is not None:
            reason = vcf_identity_reason(vcf_evidence, chromosome, position, entry)
            call = (ZygosityCall(Zygosity.UNKNOWN, None, allele=entry.alt_allele, note=reason)
                    if reason else call_vcf_zygosity(vcf_evidence, entry.ref_allele, entry.alt_allele))
        else:
            call = call_zygosity(genotype, entry.ref_allele, entry.alt_allele)
        entry.display_rank = _rank_clinvar(entry)
        if call.alt_copies is None:
            entry.allele_match, entry.allele_match_note = "unknown", call.note or "allele not recorded"
            unknown.append((entry, call))
        elif call.alt_copies > 0:
            entry.allele_match = "carried"
            entry.allele_match_note = f"{call.alt_copies} {'copy' if call.alt_copies == 1 else 'copies'} of {call.allele}" + (
                " (genotype read on the opposite strand)" if call.strand_flipped else "")
            carried.append((entry, call))
        else:
            entry.allele_match, entry.allele_match_note = "absent", f"no copy of {call.allele}"
            absent.append((entry, call))

    if trace is not None:
        for entry, call in carried:
            trace.add(rsid or entry.rsid, "clinvar", tr.source_identity("clinvar", entry), tr.RETAINED,
                      tr.STAGE_ALLELE, "allele_carried", entry.allele_match_note)
        for entry, call in unknown:
            code = tr.reason_from_note(call.note)
            stage = tr.STAGE_IDENTITY if code in (
                "vcf_build_undeclared", "source_identity_unavailable", "build_mismatch",
                "chromosome_unsupported", "mitochondrial_unsupported", "chromosome_mismatch",
                "position_mismatch",
            ) else tr.STAGE_ALLELE
            note = call.note
            if carried:
                note = f"{call.note}; not shown: an allele-specific record at this site was matched"
            trace.add(rsid or entry.rsid, "clinvar", tr.source_identity("clinvar", entry), tr.UNRESOLVED,
                      stage, code, note)
        for entry, call in absent:
            trace.add(rsid or entry.rsid, "clinvar", tr.source_identity("clinvar", entry), tr.REJECTED,
                      tr.STAGE_ALLELE, "allele_absent", entry.allele_match_note)

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
    trace: Optional[MatchTrace] = None, rsid: Optional[str] = None,
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
    carried: Optional[ZygosityCall] = None
    calls: Dict[str, ZygosityCall] = {}
    for e in entries:
        allele = (e.risk_allele or "").upper()
        if not allele:
            if trace is not None:
                trace.add(rsid or e.rsid, "gwas", tr.source_identity("gwas", e), tr.UNRESOLVED,
                          tr.STAGE_ALLELE, "risk_allele_not_recorded", "the catalogue names no risk allele")
            continue
        call = calls.get(allele)
        if call is None:
            forward, flipped = allele, False
            if (
                site_alleles and allele not in site_alleles and not ambiguous
                and _COMPLEMENT.get(allele) in site_alleles
            ):
                forward, flipped = _COMPLEMENT[allele], True
            call = call_zygosity(genotype, None, forward)
            if flipped and call.alt_copies is not None:
                call = ZygosityCall(
                    call.zygosity, call.alt_copies, allele, strand_flipped=True, allele_role="risk",
                )
            calls[allele] = call
            if call.alt_copies:
                carried = carried or call
            elif call.alt_copies is None:
                unknown = unknown or call
            else:
                absent = absent or call
        if trace is not None:
            flip = " (risk allele read on the opposite strand)" if call.strand_flipped else ""
            if call.alt_copies:
                trace.add(rsid or e.rsid, "gwas", tr.source_identity("gwas", e), tr.RETAINED, tr.STAGE_ALLELE,
                          "risk_allele_carried", f"{call.alt_copies} of risk allele {allele}{flip}")
            elif call.alt_copies is None:
                trace.add(rsid or e.rsid, "gwas", tr.source_identity("gwas", e), tr.UNRESOLVED, tr.STAGE_ALLELE,
                          tr.reason_from_note(call.note), call.note)
            else:
                trace.add(rsid or e.rsid, "gwas", tr.source_identity("gwas", e), tr.REJECTED, tr.STAGE_ALLELE,
                          "risk_allele_absent", f"no copy of risk allele {allele}{flip}")
    if carried is not None:
        return carried
    if unknown is not None:
        return unknown
    return absent


_PGX_COMPLEMENT = {"A": "T", "T": "A", "C": "G", "G": "C"}


def _match_pgx(
    genotype: Optional[str],
    rows: List[Dict[str, Any]],
    site_alleles: Optional[set] = None,
    min_level: str = PGX_DEFAULT_MIN_LEVEL,
    trace: Optional[MatchTrace] = None, rsid: Optional[str] = None,
) -> List[PGxEntry]:
    """The ClinPGx rows whose genotype is this person's genotype.

    ClinPGx writes genotypes as two forward-strand letters ("CT"); order does
    not matter. If the person's letters are not among those the annotation
    uses on either allele but their complements are, and the site is not
    A/T or C/G (where a flip is undetectable), the complement is used and
    the entry flagged. Rows below ``min_level`` are dropped. Best level first.
    """
    alleles = genotype_alleles(genotype)
    if not rows:
        return []

    def decide(r, decision, stage, reason, note=None):
        if trace is not None:
            trace.add(rsid or r.get("rsid"), "clinpgx", tr.source_identity("clinpgx", r), decision, stage, reason, note)

    if len(alleles) != 2:
        for r in rows:
            decide(r, tr.UNRESOLVED, tr.STAGE_ALLELE, "genotype_unavailable",
                   "no diploid SNP genotype to match the annotation's genotype against")
        return []
    key = "".join(sorted(alleles))
    max_rank = pgx_level_rank(min_level)
    usable = []
    for r in rows:
        if pgx_level_rank(r.get("level")) <= max_rank:
            usable.append(r)
        else:
            decide(r, tr.REJECTED, tr.STAGE_LEVEL, "pgx_below_min_level",
                   f"level {r.get('level')} is below the reporting threshold {min_level}")
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
    for r in usable:
        if matched and r in matched:
            decide(r, tr.RETAINED, tr.STAGE_APPLICABILITY, "pgx_genotype_matched",
                   f"annotation written for genotype {r.get('genotype')}"
                   + (" (genotype read on the opposite strand)" if flipped else ""))
        else:
            decide(r, tr.REJECTED, tr.STAGE_APPLICABILITY, "pgx_other_genotype",
                   f"annotation is for genotype {r.get('genotype')}, not {key}")
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


def _allele_anchor(
    clinvar_rows: List[Dict[str, Any]], matched_allele: Optional[str],
    vcf_evidence: Optional[VCFEvidence], chromosome: Optional[str], position: Optional[int],
) -> Optional[AlleleAnchor]:
    """The checked identity of the matched allele, or None.

    Preferred anchor: a ClinVar row at the rsID with full source identity
    whose ALT is the matched allele (the row the genotype matched), with
    the row's own REF. Otherwise, declared VCF evidence for the site.
    Consumer-array rows declare no build, so a GWAS- or PGx-only finding
    from one has no anchor and its frequency stays unverified.
    """
    allele = (matched_allele or "").upper()
    if not allele:
        return None
    identified = [
        row for row in clinvar_rows
        if row.get("assembly") and row.get("chromosome") and row.get("position_vcf") and row.get("ref_allele")
    ]
    for row in identified:
        if (row.get("alt_allele") or "").upper() == allele:
            return AlleleAnchor(row["assembly"], str(row["chromosome"]), int(row["position_vcf"]),
                                row["ref_allele"].upper(), allele, "the matched ClinVar record")
    for row in identified:
        # The matched allele (a GWAS risk allele, say) is the site's reference
        # allele: an anchor whose ALT is its REF, so a frequency record for
        # the alternate is reported as describing the other allele.
        if row["ref_allele"].upper() == allele:
            return AlleleAnchor(row["assembly"], str(row["chromosome"]), int(row["position_vcf"]),
                                allele, allele, "the ClinVar record for this site")
    if vcf_evidence is not None:
        build = declared_build(vcf_evidence.reference_declaration)
        if build and chromosome and isinstance(position, int) and vcf_evidence.reference:
            return AlleleAnchor(build, str(chromosome), position, vcf_evidence.reference.upper(),
                                allele, "the declared VCF record")
    return None


def _gnomad_entries(rsid: str, rows: List[Dict[str, Any]], anchor: Optional[AlleleAnchor]):
    """Every frequency record at the rsID, each checked against the anchor.

    Returns (entries, selected): ``selected`` is the one matched record, or
    the only record when nothing matched (kept as flagged context), or None.
    """
    entries: List[GnomADEntry] = []
    for gn in rows:
        identity, note = frequency_identity(gn, anchor)
        entries.append(GnomADEntry(
            rsid=gn.get("rsid", rsid),
            **{k: gn.get(k) for k in (
                "allele_frequency", "af_popmax", "ac", "an", "nhomalt",
                "af_afr", "af_eas", "af_fin", "af_nfe", "af_sas",
                "position", "assembly", "source_version",
            )},
            chromosome=gn.get("chromosome") or None,
            ref_allele=gn.get("ref_allele") or None,
            alt_allele=gn.get("alt_allele") or None,
            identity=identity, identity_note=note,
        ))
    matched = [e for e in entries if e.describes_matched_allele]
    if len(matched) == 1:
        return entries, matched[0]
    if not matched and len(entries) == 1:
        return entries, entries[0]
    return entries, None


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

    # Collapse only exactly agreeing observations. Conflicts never depend on
    # input order, including differences in VCF phase/build/filter evidence.
    grouped = {}
    for variant in variants:
        rsid = getattr(variant, 'rsid', str(variant))
        grouped.setdefault(rsid, []).append(variant)
    rsid_to_variant = {}
    for rsid, rows in grouped.items():
        if not rsid or not rsid.startswith('rs'):
            stats.dispositions[rsid] = 'unsupported_identifier'
        elif any(row != rows[0] for row in rows[1:]):
            stats.dispositions[rsid] = 'conflicting_input'
            stats.conflicting_input_sites += 1
        else:
            rsid_to_variant[rsid] = rows[0]
            stats.duplicate_rows += len(rows) - 1
            stats.dispositions[rsid] = 'no_annotation'
    rsids = list(rsid_to_variant)
    if not rsids:
        return [], stats

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

    for rsid in rsids:
        data = lookup_results.get(rsid) or {"clinvar": [], "gwas": []}
        pgx_rows = pgx_by_rsid.get(rsid) or []
        annotated = bool(data["clinvar"] or data["gwas"] or pgx_rows)
        if annotated:
            stats.annotated_sites += 1

        # Get variant metadata
        original_variant = rsid_to_variant.get(rsid)
        chromosome = getattr(original_variant, 'chromosome', None)
        position = getattr(original_variant, 'position', None)
        genotype = getattr(original_variant, 'genotype', None)

        vcf_evidence = getattr(original_variant, 'vcf_evidence', None)
        trace = stats.trace
        filter_reason = vcf_filter_reason(vcf_evidence)
        if filter_reason:
            # Do not let rejected genotypes enter any source-specific matcher.
            # Every candidate at the site is rejected at the filter stage.
            if annotated:
                stats.vcf_filter_failed_sites += 1
            for source, rows in (("clinvar", data["clinvar"]), ("gwas", data["gwas"]),
                                 ("clinpgx", pgx_rows), ("gnomad", data.get("gnomad") or [])):
                for row in rows:
                    trace.add(rsid, source, tr.source_identity(source, row), tr.REJECTED, tr.STAGE_FILTER,
                              "vcf_filter_failed", filter_reason)
            stats.dispositions[rsid] = "failed_filter"
            continue
        if not annotated:
            continue
        # Do not let non-SNP sequences reach legacy SNP/GWAS/PGx matching as
        # concatenated bases. Their complete alleles remain in source evidence.
        non_snp = vcf_evidence is not None and any(
            a not in {"A", "C", "G", "T"}
            for a in (vcf_evidence.reference,) + vcf_evidence.alternates
        )
        if non_snp:
            genotype = "--"
            for source, rows in (("gwas", data["gwas"]), ("clinpgx", pgx_rows)):
                for row in rows:
                    trace.add(rsid, source, tr.source_identity(source, row), tr.UNRESOLVED, tr.STAGE_ALLELE,
                              "non_snp_unsupported", "VCF non-SNP record requires build-aware normalization")

        # ClinVar rows that apply to this genotype (allele-aware)
        clinvar_entries, call, is_reference = _select_clinvar_rows(
            genotype, data["clinvar"], vcf_evidence, chromosome, position, trace=trace, rsid=rsid
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
        gwas_judged = False
        if gwas_entries and (is_reference or call is None):
            gwas_judged = True
            site_alleles = {
                a for cv in data["clinvar"] for a in (cv.get("ref_allele"), cv.get("alt_allele")) if a
            }
            gcall = _gwas_call(genotype, gwas_entries, site_alleles,
                               trace=None if non_snp else trace, rsid=rsid)
            if gcall is not None and gcall.alt_copies == 0:
                gwas_reference = True
            elif is_reference or call is None:
                call = gcall if gcall is not None else call

        # ClinPGx: the annotation rows written for this person's genotype
        site_alleles_pgx = {
            a for cv in data["clinvar"] for a in (cv.get("ref_allele"), cv.get("alt_allele")) if a
        }
        pgx_entries = _match_pgx(genotype, pgx_rows, site_alleles_pgx, pgx_min_level,
                                 trace=None if non_snp else trace, rsid=rsid)

        site_is_reference = (
            (is_reference or not clinvar_entries) and (gwas_reference or not gwas_entries)
            and not pgx_entries
        )
        if site_is_reference:
            stats.reference_genotype_sites += 1
            if not include_reference:
                stats.dispositions[rsid] = "reference_or_no_applicable_annotation"
                continue
            if call is None:
                call = ZygosityCall(Zygosity.HOMOZYGOUS_REFERENCE, 0)
        elif is_reference:
            # ClinVar rows do not apply; only the GWAS association remains.
            clinvar_entries = []
        elif gwas_reference:
            gwas_entries = []
        if gwas_entries and not gwas_judged and call is not None and call.alt_copies:
            # ClinVar decided the genotype; the associations ride along on the
            # ClinVar call and were not judged against their own risk allele.
            for e in gwas_entries:
                trace.add(rsid, "gwas", tr.source_identity("gwas", e), tr.RETAINED, tr.STAGE_APPLICABILITY,
                          "reported_with_clinvar_match",
                          "association shown with the ClinVar allele match; risk allele not judged separately")
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

        # Frequency records at the rsID, checked against the identity of the
        # allele the person carries; only a verified match may rank or be
        # described as this allele's frequency.
        matched_allele = call.allele if call is not None else None
        if call is not None and call.strand_flipped and call.allele_role == "risk":
            # A flipped GWAS call keeps the catalogue's name for the allele;
            # the forward-strand base is what the site's records are keyed on.
            matched_allele = _COMPLEMENT.get(matched_allele or "", matched_allele)
        anchor = _allele_anchor(data["clinvar"], matched_allele, vcf_evidence, chromosome, position)
        gnomad_entries, gnomad_entry = _gnomad_entries(rsid, data.get("gnomad") or [], anchor)
        for e in gnomad_entries:
            if e.describes_matched_allele:
                trace.add(rsid, "gnomad", tr.source_identity("gnomad", e), tr.RETAINED, tr.STAGE_FREQUENCY,
                          "frequency_identity_matched", e.identity_note)
            elif e.identity == FREQUENCY_UNVERIFIED:
                trace.add(rsid, "gnomad", tr.source_identity("gnomad", e), tr.UNRESOLVED, tr.STAGE_FREQUENCY,
                          "frequency_identity_unverified", e.identity_note)
            else:
                trace.add(rsid, "gnomad", tr.source_identity("gnomad", e), tr.REJECTED, tr.STAGE_FREQUENCY,
                          f"frequency_{e.identity}", e.identity_note)

        # This optional frequency display penalty is not applied to PGx:
        # allele commonness does not determine drug-response applicability.
        pharmacogenomic = category == VariantCategory.PHARMACOGENOMICS.value
        adjusted_rank = (
            _calculate_frequency_adjustment(sig_rank, gnomad_entry)
            if frequency_adjustment and not pharmacogenomic else sig_rank
        )

        # Skip benign variants unless requested
        if not include_benign and adjusted_rank >= 8:
            stats.benign_sites += 1
            stats.dispositions[rsid] = "rank_filtered"
            continue

        if call is None:
            call = ZygosityCall(Zygosity.UNKNOWN, None, note="annotated allele not recorded")
        if call.alt_copies is None and call.zygosity != Zygosity.NO_CALL:
            stats.zygosity_unknown_sites += 1

        # Inheritance from ClinGen, resolved against the condition each
        # applicable assertion names rather than the gene as a whole, and the
        # carrier rule: one copy of a pathogenic allele for a condition ClinGen
        # curates as recessive is carrier status, ordered a tier below the
        # affected genotype. An unresolved or conflicting condition never is.
        clingen_entries: List[ClinGenEntry] = []
        inheritance, inheritance_note = "not curated", None
        resolution: Optional[InheritanceResolution] = None
        if clinvar_entry and clinvar_entry.gene:
            # ClinVar can list several overlapping genes ("MC1R;TUBB3"); the
            # first is the one the record is about, and a curation for a
            # neighbouring gene says nothing about this allele.
            for g in clinvar_entry.gene.split(";")[:1]:
                for row in clingen_by_gene.get(g, []):
                    clingen_entries.append(ClinGenEntry(
                        gene=row.get("gene"), disease=row.get("disease"), moi=row.get("moi"),
                        classification=row.get("classification"), report_url=row.get("report_url"),
                        mondo_id=row.get("mondo_id"),
                    ))
            for entry in clinvar_entries:
                entry.inheritance = resolve_inheritance(
                    entry.conditions, entry.condition_ids, clingen_entries
                )
            resolution = clinvar_entry.inheritance
            matched_ids = {id(m) for m in resolution.matched}
            for curation in clingen_entries:
                if id(curation) in matched_ids:
                    trace.add(rsid, "clingen", tr.source_identity("clingen", curation), tr.RETAINED,
                              tr.STAGE_CONDITION, "condition_matched_by_mondo",
                              f"{curation.mondo_id} is named by the assertion; resolution {resolution.status}")
                else:
                    reason = ("assertion_has_no_condition_identifiers"
                              if resolution.status in ("no_identifiers", "identifiers_not_stored")
                              else "condition_not_named_by_assertion")
                    trace.add(rsid, "clingen", tr.source_identity("clingen", curation), tr.REJECTED,
                              tr.STAGE_CONDITION, reason,
                              f"{curation.mondo_id or 'no MONDO id'} is not among the assertion's condition identifiers")
            inheritance, inheritance_note = resolution.inheritance, resolution.note
            if category == VariantCategory.HEALTH_CONDITIONS.value and is_carrier(
                resolution, call.alt_copies, genotype
            ):
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
            gnomad_entries=gnomad_entries,
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
            inheritance_resolution=resolution,
            pgx_entries=pgx_entries,
        )

        stats.dispositions[rsid] = "reported"
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
