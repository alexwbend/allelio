"""Explicit failed filters must not become positive or negative findings."""
from dataclasses import replace
import pytest
from allelio.parsers.base import VCFEvidence
from allelio.parsers.vcf_parser import parse_vcf
from allelio.analysis.quality import vcf_filter_reason
from allelio.analysis.zygosity import call_vcf_zygosity
from allelio.analysis.lookup import analyze_variants_with_stats
from allelio.report import generate_html_report
from allelio.web.app import app
from allelio.web.routes import _generate_html_report


@pytest.mark.parametrize('site,sample,failed', [
    ('PASS', 'PASS', False), (None, None, False), ('.', '.', False),
    ('q10', 'PASS', True), ('PASS', 'lowDP', True),
    ('q10;s50', 'lowDP', True), ('PASS;q10', None, True),
])
def test_filter_evidence_blocks_direct_count(site, sample, failed):
    e = VCFEvidence('A', ('G',), (0, 1), ('A', 'G'), False,
                    filter_status=site, genotype_filter=sample)
    assert bool(vcf_filter_reason(e)) is failed
    call = call_vcf_zygosity(e, 'A', 'G')
    assert call.alt_copies == (None if failed else 1)
    if failed:
        assert 'VCF filter failure' in call.note


class SourceDB:
    """Small source adapter; failure gating must precede all matchers."""
    def __init__(self, source):
        self.source = source

    def lookup_rsids_batch(self, rsids):
        return {'rs1': {'clinvar': [dict(rsid='rs1', ref_allele='A', alt_allele='G',
            assembly='GRCh38', chromosome='1', position_vcf=100,
            clinical_significance='Pathogenic')] if self.source == 'clinvar' else [],
            'gwas': [dict(rsid='rs1', risk_allele='G', trait='Example')] if self.source == 'gwas' else []}}

    def lookup_clingen_genes(self, genes):
        return {}

    def lookup_clinpgx(self, rsids):
        return {'rs1': [dict(rsid='rs1', genotype='AG', level='1A', gene='EXAMPLE',
            annotation_text='Genotype-specific example')]} if self.source == 'pgx' else {}


@pytest.mark.parametrize('source', ['clinvar', 'gwas', 'pgx'])
@pytest.mark.parametrize('site,sample', [('q10', 'PASS'), ('PASS', 'lowDP')])
def test_failed_calls_never_reach_source_matching(tmp_path, source, site, sample):
    p = tmp_path / 'input.vcf'
    p.write_text('##fileformat=VCFv4.3\n##reference=GRCh38\n'
        '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS\n'
        f'1\t100\trs1\tA\tG\t90\t{site}\t.\tGT:FT:GQ:DP\t0/1:{sample}:99:40\n')
    variants = parse_vcf(str(p))
    assert variants[0].genotype == 'AG'
    assert variants[0].vcf_evidence.genotype_filter == sample
    results, stats = analyze_variants_with_stats(variants, SourceDB(source), include_benign=True, include_reference=True)
    assert results == []
    assert stats.vcf_filter_failed_sites == 1 and stats.annotated_sites == 1
    assert stats.reference_genotype_sites == stats.benign_sites == 0
    # The same annotation and genotype are usable when upstream filters pass.
    variants[0].vcf_evidence = replace(variants[0].vcf_evidence, filter_status='PASS', genotype_filter='PASS')
    results, stats = analyze_variants_with_stats(variants, SourceDB(source), include_benign=True)
    assert len(results) == 1 and stats.vcf_filter_failed_sites == 0


def test_both_exports_explain_excluded_calls_even_without_findings():
    meta = {'vcf_filter_failed_sites': 3}
    for document in (generate_html_report([], {}, '', meta), _generate_html_report(meta)):
        assert '3 annotated positions' in document
        assert 'record or sample filters failed' in document
        assert 'not negative findings' in document


def test_cli_reports_filter_exclusions(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from allelio import cli
    from allelio.database.store import AllelioDB
    db = AllelioDB(str(tmp_path / 'db.sqlite'))
    db.initialize()
    db.insert_clinvar_batch([dict(rsid='rs1', ref_allele='A', alt_allele='G',
        clinical_significance='Pathogenic', gene='EXAMPLE', conditions='',
        review_status='', last_evaluated='')])
    monkeypatch.setattr(cli, 'AllelioDB', lambda: db)
    p = tmp_path / 'input.vcf'
    p.write_text('##fileformat=VCFv4.3\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS\n'
                 '1\t100\trs1\tA\tG\t90\tq10\t.\tGT\t0/1\n')
    output = tmp_path / 'report.html'
    result = CliRunner().invoke(cli.analyze, [str(p), '--no-ai', '-o', str(output)])
    assert result.exit_code == 0, result.output
    assert 'filters failed' in ' '.join(result.output.split())
    assert '1 annotated positions' in output.read_text()


def test_web_returns_exclusion_count_when_all_findings_filtered(monkeypatch):
    from fastapi.testclient import TestClient
    from allelio.web import routes
    from allelio.analysis.lookup import AnalysisResults, AnalysisStats
    class DB:
        def is_initialized(self): return True
        def close(self): pass
    class Engine:
        status = "unavailable"
        model = "none"
        async def check_connection(self): return False
        def will_explain(self): return False
    monkeypatch.setattr(routes, 'AllelioDB', DB)
    monkeypatch.setattr(routes, 'AIEngine', Engine)
    monkeypatch.setattr(routes, 'parse_genotype_file', lambda p: [object()])
    monkeypatch.setattr(routes, 'analyze_variants', lambda *a: AnalysisResults([], AnalysisStats(vcf_filter_failed_sites=2)))
    response = TestClient(app, base_url='http://127.0.0.1').post('/api/analyze',
        files={'file': ('input.vcf', b'synthetic', 'text/plain')})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['evidence_export']['schema_version'] == '1.0'
    assert payload['evidence_export']['analysis_stats']['vcf_filter_failed_sites'] == 2
    assert payload['vcf_filter_failed_sites'] == 2 and payload['results'] == []
    assert 'not a negative result' in payload['summary']


def test_web_filter_notice_clears_when_loading_an_older_report():
    import json
    import shutil
    import subprocess
    from pathlib import Path
    template = (Path(__file__).resolve().parents[1] / 'allelio/web/templates/index.html').read_text()
    start = template.index("            const filterNotice =")
    code = template[start:template.index('            // Coverage is absent', start)]
    script = '''const notice = {style: {}, textContent: ''};
const document = {getElementById: () => notice};
const render = new Function('analysisResults', 'document', CODE);
render({vcf_filter_failed_sites: 2}, document);
if (notice.style.display !== 'block' || !notice.textContent.includes('not negative findings')) throw Error('missing notice');
render({}, document);
if (notice.style.display !== 'none' || notice.textContent !== '') throw Error('stale notice');
'''.replace('CODE', json.dumps(code))
    subprocess.run([shutil.which('node') or 'node', '-e', script], check=True)
