"""Conservative checks of declared reference identity; no liftover or guessing."""
from typing import Optional


_BUILD_NAMES = {'GRCh37': 'GRCh37', 'hg19': 'GRCh37',
                'GRCh38': 'GRCh38', 'hg38': 'GRCh38'}


def declared_build(value: Optional[str]) -> Optional[str]:
    """Recognize explicit names only, not filenames, URLs, or substrings."""
    return _BUILD_NAMES.get(value)


def chromosome_name(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    name = value[3:] if value.startswith('chr') else value
    if name == 'M':
        name = 'MT'
    return name if name in {str(i) for i in range(1, 23)} | {'X', 'Y', 'MT'} else None


def vcf_identity_reason(evidence, chromosome, position, entry) -> Optional[str]:
    """None if declarations agree; otherwise a reason to abstain.

    Agreement does not authenticate a file or validate its reference sequence.
    GRCh37/hg19 mitochondrial references differ, so aliases never authorize MT.
    """
    build = declared_build(evidence.reference_declaration)
    if build is None:
        return 'VCF reference build is unknown or unsupported'
    if not entry.assembly or not entry.chromosome or entry.position_vcf is None:
        return 'ClinVar reference identity unavailable; refresh reference data'
    if build != entry.assembly:
        return 'VCF and ClinVar reference builds differ'
    source_chr, input_chr = chromosome_name(entry.chromosome), chromosome_name(chromosome)
    if input_chr is None or source_chr is None:
        return 'unsupported chromosome identity'
    if input_chr == 'MT' or source_chr == 'MT':
        return 'mitochondrial reference identity requires sequence-specific matching'
    if input_chr != source_chr:
        return 'VCF and ClinVar chromosomes differ'
    if not isinstance(position, int) or position <= 0 or position != entry.position_vcf:
        return 'VCF and ClinVar positions differ'
    return None
