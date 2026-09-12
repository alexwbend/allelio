"""Deterministic gene grouping over existing findings, without risk aggregation."""
import re
from html import escape

# Short original paraphrases of MedlinePlus Genetics normal-function sections.
# The catalogue is deliberately limited; do not generate missing functions.
FUNCTION_VERSION = '2026-09-12'
FUNCTIONS = {
    'BRCA1': 'Helps repair damaged DNA and maintain the stability of genetic information.',
    'BRCA2': 'Helps repair breaks in DNA and maintain the stability of genetic information.',
    'CFTR': 'Forms a chloride channel that helps regulate water movement and mucus consistency.',
    'APOE': 'Helps package and transport cholesterol and other fats in the bloodstream.',
    'HFE': 'Helps regulate iron absorption and storage through iron sensing and hepcidin regulation.',
}
MULTIPLE_NOTE = ('Multiple findings in a gene do not by themselves establish greater risk, '
                 'a haplotype, or compound heterozygosity. Review each finding separately.')
MISSING_FUNCTION = 'A sourced function summary is not available in this release.'


def value(item, name, default=None):
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _symbols(text):
    if not isinstance(text, str):
        return []
    return sorted({s for raw in re.split(r';|,|\s+-\s+', text) if
                   (s := raw.strip()) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', s)
                   and s.lower() not in {'unknown', 'unassigned', 'intergenic', 'nr', 'na'}})


def gene_assignments(result):
    """All source gene associations; stable IDs only when mapping is unambiguous."""
    assignments = set()
    if isinstance(result, dict):
        for entry in result.get('gene_assignments') or []:
            if not isinstance(entry, dict):
                continue
            names = _symbols(entry.get('symbol'))
            identifier = entry.get('hgnc_id')
            identifier = identifier if isinstance(identifier, str) and re.fullmatch(r'HGNC:\d+', identifier) else None
            assignments.update((name, identifier if len(names) == 1 else None) for name in names)
        if not assignments:
            assignments.update((name, None) for name in _symbols(result.get('gene')))
    else:
        for source, field in (('clinvar_entries', 'gene'), ('gwas_entries', 'mapped_gene'), ('pgx_entries', 'gene')):
            for entry in value(result, source, []) or []:
                names = _symbols(value(entry, field))
                identifier = value(entry, 'hgnc_id')
                identifier = identifier if isinstance(identifier, str) and re.fullmatch(r'HGNC:\d+', identifier) else None
                assignments.update((name, identifier if len(names) == 1 else None) for name in names)
    return [dict(symbol=s, hgnc_id=i) for s, i in sorted(assignments, key=lambda a: (a[0], a[1] or ''))]


def gene_label(result):
    """Display all recorded gene associations, including PGx-only findings."""
    return '; '.join(sorted({a['symbol'] for a in gene_assignments(result)})) or None


def group_findings(results):
    """Return JSON-compatible groups referencing input indices, before UI limits.

    Shared findings appear in each associated gene. Identical finding identities
    count once per group. Conflicting genotypes/categories remain separate.
    Symbols merge through HGNC only when the source supplies an unambiguous ID.
    """
    assignments = [gene_assignments(r) for r in results]
    symbol_ids = {}
    for row in assignments:
        for a in row:
            if a['hgnc_id']:
                symbol_ids.setdefault(a['symbol'], set()).add(a['hgnc_id'])
    groups = {}
    for index, (result, row) in enumerate(zip(results, assignments)):
        identity = tuple(str(value(result, k, '') or '') for k in
                         ('rsid', 'chromosome', 'position', 'genotype', 'matched_allele', 'category'))
        if not identity[0]:
            identity += (str(index),)
        for a in row or [dict(symbol='Unassigned', hgnc_id=None)]:
            symbol = a['symbol']
            candidates = symbol_ids.get(symbol, set())
            identifier = a['hgnc_id'] or (next(iter(candidates)) if len(candidates) == 1 else None)
            key = identifier or 'symbol:' + symbol
            group = groups.setdefault(key, dict(key=key, hgnc_id=identifier, symbols=set(),
                                                indices=[], seen=set()))
            group['symbols'].add(symbol)
            if identity not in group['seen']:
                group['seen'].add(identity)
                group['indices'].append(index)
    output = []
    for group in groups.values():
        symbols = sorted(group['symbols'])
        # Do not ascribe a catalogue function to a group of unresolved aliases.
        symbol = symbols[0] if len(symbols) == 1 else None
        function = FUNCTIONS.get(symbol)
        output.append(dict(key=group['key'], hgnc_id=group['hgnc_id'],
            gene=' / '.join(symbols), symbols=symbols, indices=group['indices'],
            count=len(group['indices']), function=function or MISSING_FUNCTION,
            function_source=(f'https://medlineplus.gov/genetics/gene/{symbol.lower()}/' if function else None),
            function_version=FUNCTION_VERSION if function else None,
            note=MULTIPLE_NOTE if len(group['indices']) > 1 else 'Interpret this finding using its own evidence.'))
    return sorted(output, key=lambda g: (g['gene'] == 'Unassigned', g['gene']))


def gene_overview_html(results):
    """Escaped, expandable overview linked to canonical finding details."""
    if not results:
        return ''
    out = ['<section class="gene-overview"><h2>Findings by gene</h2>',
           '<p>Counts cover the findings in this report, not all variants in the gene. '
           'A finding associated with several genes appears in each group.</p>']
    for group in group_findings(results):
        out.append(f'<details class="gene-group"><summary>{escape(group["gene"])} — '
                   f'{group["count"]} {"finding" if group["count"] == 1 else "findings"}</summary><p>{escape(group["function"])}</p>')
        if group['function_source']:
            out.append(f'<p><a href="{group["function_source"]}">MedlinePlus Genetics</a> '
                       f'(summary version {FUNCTION_VERSION})</p>')
        out.append(f'<p>{escape(group["note"])}</p><ul>')
        for index in group['indices']:
            result = results[index]
            out.append(f'<li><a href="#finding-{index}">{escape(str(value(result, "rsid", "Unknown")))}</a>'
                       f' — {escape(str(value(result, "category", "Unknown")))}</li>')
        out.append('</ul></details>')
    return ''.join(out) + '</section>'
