"""23andMe format genotype file parser.

This module parses genotype files from 23andMe in their standard tab-delimited format.

Format specification:
- Tab-delimited file with 4 columns
- Columns: rsid, chromosome, position, genotype
- Comment lines start with '#'
- No-calls are represented as '--' and are skipped
- Valid rsid format starts with 'rs' or 'i'
"""

import gzip
from dataclasses import dataclass
from typing import List, Generator, Optional, Tuple

from .base import Variant


@dataclass
class ParseStats:
    """Row-level counts of identifier type from a 23andMe file.

    A 23andMe raw file has two kinds of variant identifiers: standard dbSNP
    rsIDs, and 23andMe's internal `i`-prefixed probe IDs for variants the
    standard array chemistry doesn't cover well — disproportionately
    clinically important ones (see README "Known gaps: 23andMe internal
    IDs"). Every lookup in allelio/analysis/lookup.py is keyed by rsID, so
    `i`-ID rows are parsed but never annotated. This is not a mapping fix —
    it exists so that gap is counted and disclosed rather than silent.
    """
    total_rows: int = 0
    rs_id_rows: int = 0
    i_id_rows: int = 0


def _parse_23andme_lines(
    filepath: str, stats: Optional[ParseStats] = None
) -> Generator[Variant, None, None]:
    """Generate Variant objects from a 23andMe format file.

    Args:
        filepath: Path to the 23andMe format file (can be gzipped)
        stats: If given, updated in place with counts of rs- vs i-ID rows.

    Yields:
        Variant objects for each valid line in the file
    """
    # Open file with gzip if needed
    file_opener = gzip.open if filepath.endswith('.gz') else open

    with file_opener(filepath, 'rt', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.rstrip('\n')

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Parse tab-delimited line
            parts = line.split('\t')
            if len(parts) < 4:
                continue

            rsid, chromosome, position_str, genotype = parts[0], parts[1], parts[2], parts[3]

            # Validate rsid format (must start with 'rs' or 'i')
            if not (rsid.startswith('rs') or rsid.startswith('i')):
                continue

            # Skip no-calls
            if genotype == '--':
                continue

            # Parse position as integer
            try:
                position = int(position_str)
            except ValueError:
                continue

            if stats is not None:
                stats.total_rows += 1
                if rsid.startswith('rs'):
                    stats.rs_id_rows += 1
                else:
                    stats.i_id_rows += 1

            # Yield valid variant
            yield Variant(
                rsid=rsid,
                chromosome=chromosome,
                position=position,
                genotype=genotype
            )


def parse_23andme(filepath: str) -> List[Variant]:
    """Parse a 23andMe format genotype file.

    Args:
        filepath: Path to the 23andMe format file (can be gzipped)

    Returns:
        List of Variant objects parsed from the file
    """
    return list(_parse_23andme_lines(filepath))


def parse_23andme_with_stats(filepath: str) -> Tuple[List[Variant], ParseStats]:
    """Parse a 23andMe file and count rows by identifier type.

    Identical to parse_23andme, but also reports how many data rows used a
    standard rsID versus 23andMe's internal i-prefixed probe IDs — see
    ParseStats. This does not resolve i-ID rows to anything; it counts them
    so the gap can be disclosed (README, paper.md Limitations, and the
    `allelio analyze`/`allelio info` output) instead of silently dropped.

    Args:
        filepath: Path to the 23andMe format file (can be gzipped)

    Returns:
        (variants, stats) — the same list parse_23andme would return, plus
        the row counts collected while parsing it.
    """
    stats = ParseStats()
    variants = list(_parse_23andme_lines(filepath, stats))
    return variants, stats
