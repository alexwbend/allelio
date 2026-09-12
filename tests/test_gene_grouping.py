"""Gene grouping conserves findings and does not combine their clinical meaning."""
from types import SimpleNamespace
import re
from allelio.analysis.genes import group_findings, gene_assignments, gene_overview_html, MULTIPLE_NOTE
from allelio.analysis.lookup import VariantResult, ClinVarEntry, PGxEntry, GWASEntry
from allelio.report import generate_html_report
from allelio.web.app import app  # Initialize routes through the app.
from allelio.web.routes import _generate_html_report


def finding(rsid='rs1', gene='BRCA2', category='Health Conditions'):
    return VariantResult(rsid=rsid, genotype='AG', chromosome='1', position=100,
        category=category, significance_rank=1,
        clinvar_entries=[ClinVarEntry(rsid=rsid, gene=gene, clinical_significance='Pathogenic')])


def test_distinct_counts_and_multiple_gene_membership():
    first = finding(gene='BRCA2;CFTR')
    results = [first, first, finding('rs2'), finding('rs3', None)]
    groups = {g['gene']:g for g in group_findings(results)}
    assert groups['BRCA2']['indices'] == [0, 2]
    assert groups['BRCA2']['count'] == 2
    assert groups['CFTR']['indices'] == [0]
    assert groups['Unassigned']['indices'] == [3]
    assert groups['BRCA2']['note'] == MULTIPLE_NOTE
    assert sorted({i for g in groups.values() for i in g['indices']}) == [0, 2, 3]


def test_all_sources_and_hyphenated_symbols():
    result = finding(gene='HLA-DQA1')
    result.gwas_entries = [GWASEntry(rsid='rs1', mapped_gene='HLA-DQB1 - HLA-DQA1')]
    result.pgx_entries = [PGxEntry(rsid='rs1', annotation_id='1', gene='CYP2D6')]
    assert {a['symbol'] for a in gene_assignments(result)} == {'HLA-DQA1','HLA-DQB1','CYP2D6'}


def test_shared_stable_id_merges_source_aliases():
    a, b = finding(gene='OLD'), finding('rs2', 'NEW')
    a.clinvar_entries[0].hgnc_id = b.clinvar_entries[0].hgnc_id = 'HGNC:1'
    group, = group_findings([a,b])
    assert group['hgnc_id'] == 'HGNC:1' and group['count'] == 2
    assert group['symbols'] == ['NEW','OLD']
    assert group['function_source'] is None


def test_conflicting_ids_do_not_force_merge():
    a, b, c = finding(), finding('rs2'), finding('rs3')
    a.clinvar_entries[0].hgnc_id = 'HGNC:1'
    b.clinvar_entries[0].hgnc_id = 'HGNC:2'
    assert len(group_findings([a,b,c])) == 3


def test_json_projection_preserves_groups():
    results = [finding(), finding('rs2', 'CFTR')]
    projected = [dict(rsid=r.rsid, chromosome=r.chromosome, position=r.position,
                      genotype=r.genotype, category=r.category, gene_assignments=gene_assignments(r)) for r in results]
    assert group_findings(projected) == group_findings(results)


def test_unassigned_and_untrusted_text_are_not_lost_or_executed():
    rows = [dict(rsid='<script>alert(1)</script>', gene='<img src=x>', category='<b>unsafe</b>')]
    html = gene_overview_html(rows)
    assert 'Unassigned' in html and '&lt;script&gt;' in html
    assert '<script>' not in html and '<img' not in html


def test_report_links_reach_all_findings_including_past_previous_limit():
    results = [finding(f'rs{i}') for i in range(102)] + [finding('rs999', None, 'Unknown')]
    html = generate_html_report(results, {}, '', {})
    links = re.findall(r'href="#(finding-\d+)"', html)
    assert len(links) == 103
    assert all(f'id="{target}"' in html for target in links)
    assert 'MedlinePlus Genetics' in html and 'compound heterozygosity' in html


def test_web_export_group_links_and_uncategorized_rows():
    results = [dict(rsid=f'rs{i}', gene='BRCA2', category='Unknown', genotype='AG') for i in range(102)]
    html = _generate_html_report(dict(results=results))
    assert '102 findings' in html
    assert 'id="finding-101"' in html
    assert '<script>' not in html


def test_cli_gene_summary_includes_findings_beyond_top(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from allelio import cli
    from allelio.database.store import AllelioDB
    db = AllelioDB(str(tmp_path / 'a.db'))
    db.initialize()
    db.insert_clinvar_batch([dict(rsid=f'rs{i}', gene='BRCA2', clinical_significance='Pathogenic',
        ref_allele='A', alt_allele='G', review_status='', conditions='', last_evaluated='') for i in (1,2)])
    monkeypatch.setattr(cli, 'AllelioDB', lambda: db)
    path = tmp_path / 'input.txt'
    path.write_text('# synthetic\nrs1\t1\t100\tAG\nrs2\t1\t101\tAG\n')
    result = CliRunner().invoke(cli.analyze, [str(path), '--no-ai', '--top', '1', '-o', str(tmp_path / 'report.html')])
    assert result.exit_code == 0, result.output
    assert 'Findings by gene' in result.output
    # rs2 is not in the top-one variant table but is in the gene summary.
    assert 'rs2' in result.output
    assert 'BRCA2' in result.output


def test_actual_web_group_renderer_filters_and_keeps_unlisted_rows():
    import json
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which('node')
    assert node, 'Node is needed for the web grouping test'
    results = [dict(rsid='rs1', category='Traits', gene='BRCA2'),
               dict(rsid='rs2', category='Health Conditions', gene='BRCA2'),
               dict(rsid='rs3', category='Traits', gene=None)]
    groups = group_findings(results)
    # Deliberately omit Unassigned to exercise stale/incomplete saved metadata.
    payload = dict(results=results, gene_groups=[g for g in groups if g['gene'] != 'Unassigned'])
    template = (Path(__file__).resolve().parents[1] / 'allelio/web/templates/index.html').read_text()
    def fenced(name):
        return template.split(f'// {name} start')[1].split(f'// {name} end')[0]
    script = '''
const element = tag => ({tag, children: [], appendChild(child) {this.children.push(child);}});
const container = element('container');
const document = {getElementById: () => container, createElement: element};
const createResultCard = result => ({tag:'card', rsid:result.rsid});
const renderAttribution = () => {};
let currentCategory = 'traits';
''' + 'const analysisResults = ' + json.dumps(payload) + ';\n' + fenced('slugify') + fenced('render-cards') + '''
renderResultCards();
console.log(JSON.stringify(container));
'''
    completed = subprocess.run([node, '-e', script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    tree = json.loads(completed.stdout)
    serialized = json.dumps(tree)
    assert '1 of 2 findings' in serialized
    assert 'rs1' in serialized and 'rs3' in serialized and 'rs2' not in serialized


def test_pgx_only_gene_label_matches_its_group():
    from allelio.analysis.genes import gene_label
    from allelio.report import _get_gene
    from allelio.web.routes import _gene_of
    result = finding(gene=None)
    result.clinvar_entries = []
    result.pgx_entries = [PGxEntry(rsid='rs1', annotation_id='1', gene='CYP2D6')]
    assert gene_label(result) == _get_gene(result) == _gene_of(result) == 'CYP2D6'
    assert group_findings([result])[0]['gene'] == 'CYP2D6'
