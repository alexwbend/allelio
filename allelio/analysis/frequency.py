"""Validation shared by frequency display and ranking.

A population frequency describes one allele at one position of one reference
build. Before a frequency is shown as the matched allele's, or allowed to
move a finding's display rank, its recorded identity has to agree with the
identity of the allele the person carries. Nothing here lifts over builds,
flips strands, or guesses: a record that cannot be checked is kept as
unverified context and says so.
"""
import math
from dataclasses import dataclass
from typing import Optional, Tuple

from allelio.analysis.identity import chromosome_name

# Identity outcomes for one frequency record against the matched allele.
MATCHED = "matched"
UNVERIFIED = "unverified"            # no allele in the record, or nothing to compare to
BUILD_MISMATCH = "build_mismatch"
POSITION_MISMATCH = "position_mismatch"
OTHER_ALLELE = "other_allele"        # same site, a different alternate allele
ALLELES_SWAPPED = "alleles_swapped"  # record's REF is the matched allele
ORIENTATION_REVERSED = "orientation_reversed"  # record on the opposite strand
ALLELE_MISMATCH = "allele_mismatch"

_COMPLEMENT = {"A": "T", "T": "A", "C": "G", "G": "C"}

REFRESH_HINT = "refresh the frequency extract (allelio update) for allele-aware records"


@dataclass(frozen=True)
class AlleleAnchor:
    """The identity of the allele a finding is about, from a checked source.

    Built from the ClinVar row the person's genotype matched (its assembly,
    chromosome, VCF position, REF and the matched ALT), or from declared VCF
    evidence. Never from a filename or an assumed build. ``alt == ref``
    means the matched allele is the site's reference allele, which no
    alternate-allele frequency record describes.
    """
    assembly: str
    chromosome: str
    position: int
    ref: str
    alt: str
    source: str


def valid_frequency(value) -> bool:
    """Accept finite numeric proportions, never booleans or coerced strings."""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 <= value <= 1)


def _complement(sequence: str) -> Optional[str]:
    try:
        return "".join(_COMPLEMENT[b] for b in sequence)
    except KeyError:
        return None


def frequency_identity(record, anchor: Optional[AlleleAnchor]) -> Tuple[str, str]:
    """Compare a frequency record's identity with the matched allele's.

    ``record`` needs ``assembly``, ``chromosome``, ``position``,
    ``ref_allele`` and ``alt_allele`` attributes or keys. Returns
    ``(identity, note)``; only ``MATCHED`` licenses describing the
    frequency as this allele's or applying the display penalty.
    """
    get = record.get if isinstance(record, dict) else lambda k, d=None: getattr(record, k, d)
    ref, alt = (get("ref_allele") or "").upper(), (get("alt_allele") or "").upper()
    if not ref or not alt:
        return UNVERIFIED, f"frequency record carries no allele identity (rsID-only extract); {REFRESH_HINT}"
    if anchor is None:
        return UNVERIFIED, "no checked source identity to compare the frequency record against"
    assembly = get("assembly")
    if not assembly:
        return UNVERIFIED, "frequency extract declares no assembly"
    if assembly != anchor.assembly:
        return BUILD_MISMATCH, f"frequency record is {assembly}; the matched allele is {anchor.assembly}"
    record_chr, anchor_chr = chromosome_name(get("chromosome")), chromosome_name(anchor.chromosome)
    position = get("position")
    if record_chr is None or record_chr != anchor_chr or position != anchor.position:
        return POSITION_MISMATCH, (
            f"frequency record is at {get('chromosome') or '?'}:{position if position is not None else '?'}; "
            f"the matched allele is at {anchor.chromosome}:{anchor.position}"
        )
    if anchor.ref == anchor.alt:
        return OTHER_ALLELE, (
            f"the matched allele {anchor.alt} is the reference allele at this site; "
            f"the frequency record describes the alternate {ref}>{alt}"
        )
    if ref == anchor.ref and alt == anchor.alt:
        return MATCHED, f"{assembly} {anchor.chromosome}:{anchor.position} {ref}>{alt} agrees with {anchor.source}"
    if ref == anchor.alt and alt == anchor.ref:
        return ALLELES_SWAPPED, f"frequency record is {ref}>{alt}; its REF is the matched allele {anchor.alt}"
    if _complement(ref) == anchor.ref and _complement(alt) == anchor.alt:
        return ORIENTATION_REVERSED, (
            f"frequency record {ref}>{alt} is the opposite strand of the matched {anchor.ref}>{anchor.alt}; "
            "not flipped, resolve it in the extract"
        )
    if ref == anchor.ref:
        return OTHER_ALLELE, f"frequency record describes {ref}>{alt}, not the matched {anchor.ref}>{anchor.alt}"
    return ALLELE_MISMATCH, f"frequency record {ref}>{alt} does not describe the matched {anchor.ref}>{anchor.alt}"
