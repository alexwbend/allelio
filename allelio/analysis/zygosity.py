"""Zygosity: how many copies of an annotated allele the user actually carries.

A ClinVar or GWAS Catalog row describes one allele at one position. A genotype
file says which two alleles the user has there. Matching the two is what turns
"this rsID has a pathogenic entry" into one of three very different things:

- the user carries **no copies** of the annotated allele (homozygous reference):
  the entry does not apply to them and must not be reported as a finding;
- **one copy** (heterozygous): a carrier for a recessive condition, affected for
  a dominant one;
- **two copies** (homozygous alternate), or one copy on a haploid chromosome
  (hemizygous, e.g. X in males).

Consumer files report genotypes on the forward strand of the reference build,
as do ClinVar's VCF-style alleles, so a direct comparison usually works. When
it does not, and the site is a SNP whose alleles are not their own complement
(not A/T or C/G), the complement is tried and the flip is noted. Indels come
from 23andMe as ``I``/``D`` and are matched by allele length.

Everything here is pure: no database, no I/O.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence

from allelio.parsers.base import VCFEvidence


class Zygosity(str, Enum):
    """How many copies of the annotated (alternate / risk) allele are present."""

    HOMOZYGOUS_REFERENCE = "homozygous reference"
    HETEROZYGOUS = "heterozygous"
    HOMOZYGOUS_ALTERNATE = "homozygous alternate"
    HEMIZYGOUS_ALTERNATE = "hemizygous alternate"
    HEMIZYGOUS_REFERENCE = "hemizygous reference"
    NO_CALL = "no call"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ZygosityCall:
    """The outcome of matching a genotype against an annotated allele.

    Attributes:
        zygosity: One of the ``Zygosity`` values.
        alt_copies: 0, 1 or 2 copies of the annotated allele; None if unknown.
        allele: The annotated allele that was counted, as written in the
            reference source (e.g. ``"A"``), or None.
        strand_flipped: True if the genotype only matched after complementing
            it, worth showing, since it is an inference, not a read.
        note: Short human-readable reason when the call is ``UNKNOWN``.
    """

    zygosity: Zygosity
    alt_copies: Optional[int]
    allele: Optional[str] = None
    strand_flipped: bool = False
    note: Optional[str] = None
    # "alternate" for a ClinVar row (ref and alt known); "risk" for a GWAS
    # row, which names only the allele the association was reported for.
    # That allele may be the reference allele, so "homozygous alternate"
    # would be the wrong phrase for it.
    allele_role: str = "alternate"

    @property
    def carries_allele(self) -> Optional[bool]:
        """True/False when known, None when the call is unknown."""
        if self.alt_copies is None:
            return None
        return self.alt_copies > 0

    def describe(self) -> str:
        """One phrase for a report: ``heterozygous (1 copy of the A allele)``."""
        z = self.zygosity
        if z == Zygosity.NO_CALL:
            return "no call"
        if z == Zygosity.UNKNOWN:
            return "zygosity unknown" + (f" ({self.note})" if self.note else "")
        copies = self.alt_copies
        unit = "copy" if copies == 1 else "copies"
        flipped = ", read on the opposite strand" if self.strand_flipped else ""
        if self.allele_role == "risk":
            allele = f" {self.allele}" if self.allele else ""
            if copies == 0:
                return f"no copies of the risk allele{allele}{flipped}"
            return f"{copies} {unit} of the risk allele{allele}{flipped}"
        allele = f" of the {self.allele} allele" if self.allele else ""
        return f"{z.value} ({copies} {unit}{allele}{flipped})"


_COMPLEMENT = {"A": "T", "T": "A", "C": "G", "G": "C"}
_NO_CALL_TOKENS = {"", "--", "00", "0", "NN", "N", "..", ".", "-"}


def genotype_alleles(genotype: Optional[str]) -> List[str]:
    """Split a genotype string into its alleles.

    ``"AG"`` -> ``["A", "G"]``; ``"A"`` -> ``["A"]`` (haploid);
    ``"DI"`` -> ``["D", "I"]``; no-call tokens -> ``[]``. Anything longer than
    two characters that is not a pair of single letters is treated as
    unparseable and returns ``[]`` too: better an unknown than a wrong count.
    """
    if genotype is None:
        return []
    g = str(genotype).strip().upper()
    if g in _NO_CALL_TOKENS:
        return []
    if len(g) in (1, 2) and all(ch.isalpha() for ch in g):
        return list(g)
    return []


def _is_snp(ref: str, alt: str) -> bool:
    return len(ref) == 1 and len(alt) == 1 and ref in _COMPLEMENT and alt in _COMPLEMENT


def _strand_ambiguous(ref: str, alt: str) -> bool:
    """A/T and C/G SNPs read the same on both strands; a flip cannot be detected."""
    return {ref, alt} in ({"A", "T"}, {"C", "G"})


def _count(alleles: Sequence[str], alt: str, role: str = "alternate") -> ZygosityCall:
    copies = sum(1 for a in alleles if a == alt)
    if len(alleles) == 1:
        z = Zygosity.HEMIZYGOUS_ALTERNATE if copies == 1 else Zygosity.HEMIZYGOUS_REFERENCE
        return ZygosityCall(z, copies, alt, allele_role=role)
    if copies == 0:
        return ZygosityCall(Zygosity.HOMOZYGOUS_REFERENCE, 0, alt, allele_role=role)
    if copies == 1:
        return ZygosityCall(Zygosity.HETEROZYGOUS, 1, alt, allele_role=role)
    return ZygosityCall(Zygosity.HOMOZYGOUS_ALTERNATE, 2, alt, allele_role=role)


def call_zygosity(genotype: Optional[str], ref: Optional[str], alt: Optional[str]) -> ZygosityCall:
    """Count how many copies of ``alt`` the genotype carries.

    Args:
        genotype: The user's genotype as the file reports it (``"AG"``, ``"A"``,
            ``"DI"``, ``"--"``).
        ref: The reference allele of the annotated row (may be None / "").
        alt: The annotated (alternate or risk) allele (may be None / "").

    Returns:
        A ``ZygosityCall``. ``UNKNOWN`` when the alleles are not given, when
        the genotype's letters are not among them on either strand, or when a
        strand flip would be needed at an A/T or C/G site (undetectable).
    """
    alleles = genotype_alleles(genotype)
    if not alleles:
        return ZygosityCall(Zygosity.NO_CALL, None, note="no call")

    ref = (ref or "").strip().upper()
    alt = (alt or "").strip().upper()
    if not alt or alt in ("NA", "-", "."):
        return ZygosityCall(Zygosity.UNKNOWN, None, note="annotated allele not recorded")
    if ref == alt:
        return ZygosityCall(Zygosity.UNKNOWN, None, allele=alt, note="annotation is not allele-specific")

    known = {ref, alt} - {""}

    # 1. Direct match on the forward strand.
    if all(a in known for a in alleles):
        return _count(alleles, alt, role="risk" if not ref else "alternate")

    # 1b. Only the annotated allele is known (GWAS risk alleles come this way).
    # Count it if present. If it is absent but its complement is present, a
    # strand flip cannot be ruled out, so say unknown rather than "0 copies".
    if not ref and len(alt) == 1 and alt in _COMPLEMENT:
        if alt in alleles:
            return _count(alleles, alt, role="risk")
        if _COMPLEMENT[alt] in alleles:
            return ZygosityCall(
                Zygosity.UNKNOWN, None, allele=alt, allele_role="risk",
                note=f"genotype {''.join(alleles)} may be on the opposite strand from the {alt} allele",
            )
        return _count(alleles, alt, role="risk")

    # 2. Indels: 23andMe writes I/D; match by allele length.
    if all(a in ("I", "D") for a in alleles) and ref and len(ref) != len(alt):
        alt_token = "I" if len(alt) > len(ref) else "D"
        mapped = [alt if a == alt_token else ref for a in alleles]
        return _count(mapped, alt)

    # 3. Complement strand, only where a flip is detectable.
    if _is_snp(ref, alt) and not _strand_ambiguous(ref, alt):
        flipped = [_COMPLEMENT.get(a, a) for a in alleles]
        if all(a in known for a in flipped):
            call = _count(flipped, alt)
            return ZygosityCall(call.zygosity, call.alt_copies, alt, strand_flipped=True)

    return ZygosityCall(
        Zygosity.UNKNOWN, None, allele=alt,
        note=f"genotype {''.join(alleles)} does not match annotated alleles {ref or '?'}/{alt}",
    )


def call_vcf_zygosity(evidence: VCFEvidence, ref: Optional[str], alt: Optional[str]) -> ZygosityCall:
    """Count an explicitly declared SNP allele without strand inference.

    This checks allele compatibility, not verified coordinate/build identity.
    Non-SNP records require normalization and build-aware source matching first.
    A different declared alternate can coexist with the target at a multiallelic
    site; unlike a biallelic genotype string, it need not make the count unknown.
    """
    ref = (ref or "").upper()
    alt = (alt or "").upper()
    def unknown(reason):
        return ZygosityCall(Zygosity.UNKNOWN, None, allele=alt or None, note=reason)

    options = (evidence.reference,) + evidence.alternates
    if not options or any(a not in _COMPLEMENT for a in options):
        return unknown("VCF non-SNP record requires build-aware normalization")
    if evidence.ploidy not in (1, 2) or len(evidence.alleles) != evidence.ploidy:
        return unknown("unsupported or inconsistent VCF ploidy")
    if any(i < 0 or i >= len(options) for i in evidence.allele_indices):
        return unknown("invalid VCF allele index")
    if tuple(options[i] for i in evidence.allele_indices) != evidence.alleles:
        return unknown("VCF alleles disagree with genotype indices")
    if ref not in _COMPLEMENT or alt not in _COMPLEMENT or ref == alt:
        return unknown("annotation is not SNP allele-specific")
    if ref != evidence.reference:
        return unknown("VCF reference allele does not match annotation")
    if alt not in evidence.alternates:
        return unknown("annotated alternate is not declared in VCF")
    return _count(evidence.alleles, alt)
