import json

from allelio.evidence import build_evidence_export, write_evidence_export
from allelio.parsers.base import Variant, VCFEvidence
from allelio.analysis.lookup import VariantResult, GnomADEntry, AnalysisStats


def test_round_trip_preserves_input_and_uncertainty(tmp_path):
    evidence = VCFEvidence('A', ('C', 'AT'), (1, 2), ('C', 'AT'), True,
                           reference_declaration='GRCh38', phase_set='123',
                           filter_status='PASS', depth='20')
    variants = [Variant('rs1', '1', 123, 'CAT', evidence)]
    result = VariantResult('rs1', chromosome='1', position=123, genotype='--',
                           zygosity_note='Unsupported non-SNP matching')
    document = build_evidence_export([result], variants, {'clinvar': {'version': 'test'}}, stats=AnalysisStats())
    path = tmp_path / 'evidence.json'
    write_evidence_export(document, path)
    loaded = json.loads(path.read_text())
    assert loaded['schema_version'] == '1.0'
    assert loaded['inputs'][0]['vcf_evidence']['alleles'] == ['C', 'AT']
    assert loaded['inputs'][0]['genotype'] == 'CAT'
    assert loaded['findings'][0]['genotype'] == '--'
    assert loaded['findings'][0]['input_ids'] == ['input-1']
    assert loaded['findings'][0]['zygosity_note'] == result.zygosity_note
    assert loaded['provenance']['clinvar']['version'] == 'test'


def test_all_findings_and_strict_json(tmp_path):
    results = [VariantResult('rs' + str(i)) for i in range(105)]
    results[0].gnomad_entry = GnomADEntry(rsid='rs0', allele_frequency=float('nan'))
    document = build_evidence_export(results, [], {})
    write_evidence_export(document, tmp_path / 'all.json')
    assert len(document['findings']) == 105
    assert document['findings'][0]['gnomad_entry']['allele_frequency'] is None
    assert document['findings'][0]['matched_allele'] is None
    finding_ids = {row['finding_id'] for row in document['findings']}
    for group in document['gene_groups']:
        assert set(group['finding_ids']) <= finding_ids


def test_cli_writes_evidence_and_rejects_path_collision(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from allelio import cli
    from allelio.database.store import AllelioDB
    db = AllelioDB(str(tmp_path / 'db.sqlite'))
    db.initialize()
    db.insert_clinvar_batch([dict(rsid='rs1', clinical_significance='Pathogenic',
        gene='EXAMPLE', conditions='', review_status='', last_evaluated='')])
    monkeypatch.setattr(cli, 'AllelioDB', lambda: db)
    source = tmp_path / 'input.txt'
    source.write_text('rs1\t1\t100\tAG\n')
    output = tmp_path / 'report.html'
    sidecar = tmp_path / 'evidence.json'
    result = CliRunner().invoke(cli.analyze, [str(source), '--no-ai', '-o', str(output), '--json-output', str(sidecar)])
    assert result.exit_code == 0, result.output
    assert json.loads(sidecar.read_text())['findings'][0]['clinvar_entries'][0]['gene'] == 'EXAMPLE'
    collision = CliRunner().invoke(cli.analyze, [str(source), '--json-output', str(source)])
    assert collision.exit_code != 0
    assert source.read_text() == 'rs1\t1\t100\tAG\n'
