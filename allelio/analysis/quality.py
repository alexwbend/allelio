"""Honor explicit upstream VCF filter failures without inventing thresholds."""
from typing import Optional
from allelio.parsers.base import VCFEvidence


def vcf_filter_reason(evidence: Optional[VCFEvidence]) -> Optional[str]:
    """Missing/not-applied filters do not mean PASS, but are not failures."""
    if evidence is None:
        return None
    failures = []
    for label, status in (('FILTER', evidence.filter_status),
                          ('FORMAT/FT', evidence.genotype_filter)):
        if status not in (None, '', '.', 'PASS'):
            failures.append(f'{label}={status}')
    return 'VCF filter failure: ' + '; '.join(failures) if failures else None
