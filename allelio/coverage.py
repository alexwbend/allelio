"""Conserved input-row accounting, separate from counts of findings."""
from collections import Counter
from html import escape


def build_coverage(inputs, results, stats):
    audit = getattr(inputs, 'audit', None)
    dispositions = getattr(stats, 'dispositions', {})
    reported = {r.rsid for r in results}
    rows = []
    seen = set()
    for index, variant in enumerate(inputs):
        rsid = getattr(variant, 'rsid', str(variant))
        status = dispositions.get(rsid, 'reported' if rsid in reported else 'unaccounted')
        if status == 'reported' and rsid not in reported:
            status = 'report_filtered'
        if status not in ('conflicting_input', 'unsupported_identifier') and rsid in seen:
            status = 'duplicate_row'
        seen.add(rsid)
        rows.append({'line': getattr(variant, 'source_line', None),
                     'input_id': 'input-' + str(index + 1), 'rsid': rsid, 'status': status})
    if audit is not None:
        rows.extend(dict(row) for row in audit.rows if row['status'] != 'parsed')
        rows.sort(key=lambda row: row['line'] or 0)
        total = len(audit.rows)
    else:
        total = len(inputs)
    counts = dict(sorted(Counter(row['status'] for row in rows).items()))
    return {
        'scope': 'input_data_rows' if audit is not None else 'parsed_inputs_only',
        'total_rows': total,
        'accounted_rows': len(rows),
        'counts': counts,
        'rows': rows,
        'returned_findings': len(results),
        'complete': len(rows) == total and not counts.get('unaccounted'),
        'limitations': 'Rows absent from the input cannot be counted. Coverage is not a negative genetic test or clinical sensitivity estimate.',
    }


def coverage_text(coverage):
    if not coverage:
        return ''
    counts = '; '.join(f"{key.replace('_', ' ')}: {value:,}" for key, value in coverage['counts'].items())
    scope = 'input data rows' if coverage['scope'] == 'input_data_rows' else 'parsed inputs only'
    return (f"Input coverage ({scope}): {coverage['accounted_rows']:,}/{coverage['total_rows']:,} rows accounted for. "
            + counts + '. ' + coverage['limitations'])


def coverage_html(coverage):
    text = coverage_text(coverage)
    return '<p class="gap-note">' + escape(text) + '</p>' if text else ''
