"""Candidate-level matching trace: what happened to every source record.

Matching a person's genotype against reference data considers more records
than end up in a finding: the other alternate allele at a multiallelic site,
a frequency row for a different build, a ClinPGx annotation for another
genotype, a ClinGen curation for a condition the assertion does not name.
The trace records one decision per candidate record, with a structured
reason code and the identity the source gave it, so an export can show why
a record was retained, rejected, or left unresolved instead of only what
was kept.

Decisions come from the matching functions themselves (they append to the
trace as they decide); nothing here re-implements a match.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Decisions.
RETAINED = "retained"        # the record applies to this person and fed the result
REJECTED = "rejected"        # checked and found not to apply
UNRESOLVED = "unresolved"    # could not be checked; kept without a verdict

# Stages, in the order a record meets them.
STAGE_FILTER = "filter"              # VCF FILTER / FORMAT FT
STAGE_IDENTITY = "identity"          # build, chromosome, position agreement
STAGE_ALLELE = "allele"              # does the genotype carry the record's allele
STAGE_APPLICABILITY = "applicability"  # is the record about this person's genotype
STAGE_LEVEL = "level"                # evidence-level threshold (ClinPGx)
STAGE_FREQUENCY = "frequency"        # frequency record identity
STAGE_CONDITION = "condition"        # ClinGen curation versus the assertion's condition

# Reason codes are stable identifiers; the note carries the human sentence.
# Abstention notes written by the zygosity and identity checks map onto
# codes by prefix, so the same sentence always yields the same code.
_NOTE_CODES = (
    ("no call", "genotype_no_call"),
    ("annotated allele not recorded", "allele_not_recorded"),
    ("annotation is not allele-specific", "annotation_not_allele_specific"),
    ("annotation is not SNP allele-specific", "annotation_not_allele_specific"),
    ("may be on the opposite strand", "strand_ambiguous"),
    ("does not match annotated alleles", "genotype_allele_mismatch"),
    ("VCF reference build is unknown", "vcf_build_undeclared"),
    ("ClinVar reference identity unavailable", "source_identity_unavailable"),
    ("VCF and ClinVar reference builds differ", "build_mismatch"),
    ("unsupported chromosome identity", "chromosome_unsupported"),
    ("mitochondrial reference identity", "mitochondrial_unsupported"),
    ("VCF and ClinVar chromosomes differ", "chromosome_mismatch"),
    ("VCF and ClinVar positions differ", "position_mismatch"),
    ("VCF non-SNP record requires", "non_snp_unsupported"),
    ("unsupported or inconsistent VCF ploidy", "ploidy_unsupported"),
    ("invalid VCF allele index", "vcf_index_invalid"),
    ("VCF alleles disagree with genotype indices", "vcf_alleles_inconsistent"),
    ("VCF reference allele does not match annotation", "vcf_reference_mismatch"),
    ("annotated alternate is not declared in VCF", "vcf_alternate_undeclared"),
)
UNRESOLVED_OTHER = "unresolved_other"


def reason_from_note(note: Optional[str]) -> str:
    """The reason code for an abstention note; ``unresolved_other`` if unmapped."""
    text = (note or "").strip()
    for prefix, code in _NOTE_CODES:
        if text.startswith(prefix) or prefix in text:
            return code
    return UNRESOLVED_OTHER


@dataclass
class CandidateDecision:
    """One source record at one input site, and what matching decided.

    ``identity`` is whatever identity the source gave the record (allele and
    variation IDs, assembly, chromosome, position, REF/ALT for ClinVar; study
    and risk allele for GWAS; annotation and genotype for ClinPGx; alleles and
    assembly for gnomAD; disease and MONDO id for ClinGen). ``candidate_id``
    is assigned at export time and is local to that document.
    """
    rsid: str
    source: str
    identity: Dict[str, Any]
    decision: str
    stage: str
    reason: str
    note: Optional[str] = None
    candidate_id: Optional[str] = None


@dataclass
class MatchTrace:
    """Every candidate decision of one analysis, in the order they were made."""
    candidates: List[CandidateDecision] = field(default_factory=list)

    def add(self, rsid: str, source: str, identity: Dict[str, Any], decision: str,
            stage: str, reason: str, note: Optional[str] = None) -> CandidateDecision:
        decision_record = CandidateDecision(rsid, source, identity, decision, stage, reason, note)
        self.candidates.append(decision_record)
        return decision_record

    def at(self, rsid: str) -> List[CandidateDecision]:
        return [c for c in self.candidates if c.rsid == rsid]


# What each source's identity dict is built from.
_IDENTITY_KEYS = {
    "clinvar": ("allele_id", "variation_id", "assembly", "chromosome", "position_vcf", "ref_allele",
                "alt_allele", "gene", "clinical_significance", "review_status"),
    "gwas": ("study", "pubmed_id", "trait", "risk_allele", "mapped_gene"),
    "clinpgx": ("annotation_id", "genotype", "level", "drugs", "gene"),
    "gnomad": ("assembly", "chromosome", "position", "ref_allele", "alt_allele", "source_version",
               "allele_frequency"),
    "clingen": ("gene", "disease", "mondo_id", "moi", "classification"),
}


def source_identity(source: str, record: Any) -> Dict[str, Any]:
    """The identity fields a source gave a record, from a dict or an object."""
    get = record.get if isinstance(record, dict) else (lambda k, d=None: getattr(record, k, d))
    identity = {}
    for key in _IDENTITY_KEYS.get(source, ()):
        value = get(key)
        if value not in (None, ""):
            identity[key] = value
    return identity


# Every annotation path Allelio matches, and whether its decisions are
# recorded per candidate record. A path listed as partial says what is
# missing rather than leaving the reader to guess.
PATHS = {
    "clinvar": "traced: filter, identity, allele, applicability decisions per record",
    "gwas": "traced: risk-allele decisions per association; strand inference noted",
    "clinpgx": "traced: evidence-level threshold and genotype match per annotation row",
    "gnomad": "traced: frequency-record identity per allele row",
    "clingen": "partial: curations for the leading ClinVar assertion are traced; secondary assertion resolutions are in findings",
}
