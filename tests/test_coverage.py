"""Input conservation and duplicate conflict regression fixtures."""
from dataclasses import replace
import pytest
from allelio.parsers.base import parse_genotype_file, parse_genotype_file_with_stats, Variant, VCFEvidence
from allelio.analysis.lookup import analyze_variants, AnalysisStats
from allelio.coverage import build_coverage
from allelio.evidence import build_evidence_export


class DB:
    def lookup_rsids_batch(self, rsids):
        return {rsid: {'clinvar': [], 'gwas': [dict(rsid=rsid, trait='Example', risk_allele='G')]} for rsid in rsids if rsid != 'rs9'}
    def lookup_clingen_genes(self, genes): return {}
    def lookup_clinpgx(self, rsids): return {}


@pytest.mark.parametrize('header,row', [
    ('# source\n', 'rs1\t1\t100\tAG\n'),
    ('rsid\tchromosome\tposition\tallele1\tallele2\n', 'rs1\t1\t100\tA\tG\n'),
    ('##fileformat=VCFv4.3\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS\n', '1\t100\trs1\tA\tG\t.\tPASS\t.\tGT\t0/1\n'),
])
def test_all_parsers_account_for_duplicates_and_malformed_rows(tmp_path, header, row):
    path = tmp_path / 'input.txt'
    path.write_text(header + row + row + '\nmalformed\n')
    variants = parse_genotype_file(str(path))
    results = analyze_variants(variants, DB())
    coverage = build_coverage(variants, results, results.stats)
    assert coverage['complete']
    assert coverage['total_rows'] == coverage['accounted_rows'] == 3
    assert coverage['counts'] == {'duplicate_row': 1, 'malformed_row': 1, 'reported': 1}
    assert sum(coverage['counts'].values()) == 3
    assert len({r['line'] for r in coverage['rows']}) == 3
    parsed_with_stats, _ = parse_genotype_file_with_stats(str(path))
    assert len(parsed_with_stats.audit.rows) == 3


def test_conflicts_abstain_independent_of_input_order():
    one = Variant('rs1', '1', 100, 'AG')
    for two in [replace(one, genotype='AA'), replace(one, position=101),
                replace(one, vcf_evidence=VCFEvidence('A', ('G',), (0, 1), ('A', 'G'), False))]:
        for inputs in ([one, two], [two, one]):
            results = analyze_variants(inputs, DB())
            assert not results
            assert results.stats.conflicting_input_sites == 1
            assert build_coverage(inputs, results, results.stats)['counts'] == {'conflicting_input': 2}


def test_no_calls_unknown_ids_missing_annotation_and_filters(tmp_path):
    path = tmp_path / 'input.vcf'
    path.write_text('##fileformat=VCFv4.3\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS\n'
        '1\t100\trs1\tA\tG\t.\tPASS\t.\tGT\t./1\n'
        '1\t101\t.\tA\tG\t.\tPASS\t.\tGT\t0/1\n'
        '1\t102\trs9\tA\tG\t.\tPASS\t.\tGT\t0/1\n'
        '1\t103\trs8\tA\tG\t.\tq10\t.\tGT\t0/1\n'
        '1\t104\trs2\tA\tG\t.\tPASS\t.\tGT\t0/1/1\n')
    inputs = parse_genotype_file(str(path))
    results = analyze_variants(inputs, DB())
    doc = build_evidence_export(results, inputs, {}, stats=results.stats)
    assert doc['coverage']['counts'] == dict(no_call=1, unsupported_identifier=1, no_annotation=1, failed_filter=1, unsupported_genotype=1)
    assert doc['coverage']['total_rows'] == 5
    assert doc['coverage']['complete']


def test_downstream_report_filter_is_separate():
    inputs = [Variant('rs1', '1', 100, 'AG')]
    results = analyze_variants(inputs, DB())
    assert build_coverage(inputs, [], results.stats)['counts'] == {'report_filtered': 1}
    assert build_coverage(inputs, [], AnalysisStats())['counts'] == {'unaccounted': 1}


def test_web_returns_coverage_when_all_rows_are_no_calls(monkeypatch):
    from fastapi.testclient import TestClient
    from allelio.web.app import app
    from allelio.web import routes
    class WebDB(DB):
        def is_initialized(self): return True
        def close(self): pass
    class Engine:
        status = 'unavailable'
        model = 'none'
        async def check_connection(self): return False
        def will_explain(self): return False
    monkeypatch.setattr(routes, 'AllelioDB', WebDB)
    monkeypatch.setattr(routes, 'AIEngine', Engine)
    response = TestClient(app, base_url='http://127.0.0.1').post('/api/analyze',
        files={'file': ('input.txt', b'# example\nrs1\t1\t100\t--\n', 'text/plain')})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['results'] == []
    assert payload['coverage']['counts'] == {'no_call': 1}
    assert payload['evidence_export']['coverage']['rows'][0]['line'] == 2
    assert 'not a negative result' in payload['summary']
    assert 'no call: 1' in routes._generate_html_report(payload)


def test_cli_html_and_json_agree_on_coverage(tmp_path, monkeypatch):
    import json
    from click.testing import CliRunner
    from allelio import cli
    from allelio.database.store import AllelioDB
    db = AllelioDB(str(tmp_path / 'db.sqlite'))
    db.initialize()
    db.insert_clinvar_batch([dict(rsid='rs1000', clinical_significance='Benign', gene='',
        conditions='', review_status='', last_evaluated='')])
    monkeypatch.setattr(cli, 'AllelioDB', lambda: db)
    path = tmp_path / 'input.txt'
    path.write_text('rs1\t1\t100\t--\ni1\t1\t101\tAG\nrs9\t1\t102\tAG\n')
    output = tmp_path / 'report.html'
    sidecar = tmp_path / 'evidence.json'
    result = CliRunner().invoke(cli.analyze, [str(path), '--no-ai', '-o', str(output), '--json-output', str(sidecar)])
    assert result.exit_code == 0, result.output
    coverage = json.loads(sidecar.read_text())['coverage']
    assert coverage['counts'] == dict(no_call=1, unsupported_identifier=1, no_annotation=1)
    assert coverage['accounted_rows'] == 3
    assert '3/3 rows accounted for' in output.read_text()
    assert '3/3 rows accounted for' in result.output
