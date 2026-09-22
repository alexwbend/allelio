"""Synthetic VEP-shaped development fixtures, never independent VEP evidence."""
import copy
import hashlib
import json

import pytest
from click.testing import CliRunner

from allelio.benchmark import STAGES, compare_benchmarks
from allelio.cli import allelio
from allelio.vep import import_vep


@pytest.fixture
def bundle(tmp_path):
    def resource(name, data):
        (tmp_path / name).write_text(data)
        return {'path': name, 'sha256': hashlib.sha256(data.encode()).hexdigest()}
    row = '1\t100\trs123\tA\tG\t.\tPASS\t.\tGT\t0/1'
    source = resource('input.vcf', '##fileformat=VCFv4.2\n##reference=GRCh38\n'
                      '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n' + row + '\n')
    raw = resource('raw.jsonl', json.dumps({'input': row, 'colocated_variants': [{'id': 'rs123'}]}) + '\n')
    resources = [dict(resource(kind, 'synthetic ' + kind), kind=kind, version='development-fixture')
                 for kind in ('software', 'cache')]
    manifest = {'schema': 'allelio-vep-import/1', 'split': 'development', 'license': 'MIT',
                'hardware': 'synthetic test; VEP was not executed', 'vep_version': 'synthetic-fixture',
                'assembly': 'GRCh38', 'resources': resources, 'plugins': [], 'cases': [
                    {'id': 'snp', 'input': source, 'raw_output': raw,
                     'log': resource('vep.log', 'Synthetic fixture, not a real VEP run.\n'),
                     'command': ['vep', '--offline', '--cache', '--json', '--assembly', 'GRCh38'],
                     'exit_code': 0,
                     'alignment': {'reviewer': 'synthetic-test-only', 'date': '2026-09-22',
                                   'rationale': 'Test of metadata validation; no real approval.',
                                   'approved': True, 'resource_sha256': [r['sha256'] for r in resources],
                                   'allelio_references_sha256': 'a' * 64}}]}
    return tmp_path, manifest


def run(bundle):
    root, manifest = bundle
    path = root / 'manifest.json'
    path.write_text(json.dumps(manifest))
    return import_vep(path, root / 'output')


def replace_resource(bundle, key, text):
    root, manifest = bundle
    resource = manifest['cases'][0][key]
    (root / resource['path']).write_text(text)
    resource['sha256'] = hashlib.sha256(text.encode()).hexdigest()


def test_raw_provenance_and_shared_denominators(bundle):
    root, manifest = bundle
    report = run(bundle)
    assert (root / 'output/snp/vep.jsonl').read_bytes() == (root / 'raw.jsonl').read_bytes()
    assert report['provenance'] == manifest
    assert report['cases'][0]['outcomes'] == dict.fromkeys(STAGES, 'unsupported') | {'parsing': 'parsed'}
    left = copy.deepcopy(report)
    left['tool'] = {'name': 'synthetic-primary', 'version': '1'}
    left['cases'][0]['outcomes'].update(identity_matching='matched', source_selection='selected', reporting='reported')
    comparison = compare_benchmarks(left, report)
    assert comparison['paired_opportunities'] == comparison['agreements'] == 1
    assert comparison['stages']['reporting']['excluded_opportunities'] == 1
    assert comparison['stages']['parsing']['paired_opportunities'] == 1
    left['cases'][0]['references_sha256'] = 'b' * 64
    assert compare_benchmarks(left, report)['paired_opportunities'] == 0
    with pytest.raises(ValueError, match='new output'):
        run(bundle)


@pytest.mark.parametrize('mutation,match', [
    (lambda m: m.update(split='held-out'), 'held-out'),
    (lambda m: m['cases'][0].update(exit_code=1), 'Failed VEP'),
    (lambda m: m['cases'][0].update(command=['vep', '--json']), 'offline'),
    (lambda m: m['cases'][0]['alignment'].update(approved=False), 'Approval'),
    (lambda m: m['cases'][0]['alignment'].update(resource_sha256=[]), 'fingerprints'),
    (lambda m: m['cases'][0]['input'].update(path='../outside'), 'escapes'),
    (lambda m: m['resources'][0].update(sha256='0' * 64), 'checksum'),
    (lambda m: m.update(plugins=['b' * 64]), 'Plugins'),
    (lambda m: m['cases'].append(copy.deepcopy(m['cases'][0])), 'unique'),
])
def test_refuses_invalid_provenance_without_creating_output(bundle, mutation, match):
    mutation(bundle[1])
    with pytest.raises(ValueError, match=match):
        run(bundle)
    assert not (bundle[0] / 'output').exists()


def test_same_rsid_different_coordinates_is_rejected(bundle):
    replace_resource(bundle, 'raw_output', json.dumps({'input': '1 101 rs123 A G . PASS . GT 0/1'}))
    with pytest.raises(ValueError, match='absent'):
        run(bundle)


def test_duplicate_output_is_rejected(bundle):
    root, _ = bundle
    replace_resource(bundle, 'raw_output', (root / 'raw.jsonl').read_text() * 2)
    with pytest.raises(ValueError, match='Duplicate'):
        run(bundle)


@pytest.mark.parametrize('replacement', ['.', '0/.', '2/2'])
def test_unsupported_genotypes_are_exclusions(bundle, replacement):
    root, _ = bundle
    replace_resource(bundle, 'input', (root / 'input.vcf').read_text().replace('0/1', replacement))
    assert set(run(bundle)['cases'][0]['outcomes'].values()) == {'unsupported'}


def test_array_input_is_not_scored_as_failure(bundle):
    replace_resource(bundle, 'input', '# 23andMe\nrs123\t1\t100\tAG\n')
    assert run(bundle)['cases'][0]['scope_reason'] == 'consumer_array_or_non_vcf_input'


def test_empty_successful_output_is_excluded(bundle):
    replace_resource(bundle, 'raw_output', '')
    assert run(bundle)['cases'][0]['outcomes']['parsing'] == 'excluded'


def test_cli(bundle):
    root, manifest = bundle
    path = root / 'manifest.json'
    path.write_text(json.dumps(manifest))
    result = CliRunner().invoke(allelio, ['import-vep', str(path), '--output', str(root / 'output')])
    assert result.exit_code == 0, result.output
    assert 'parsing-only' in result.output


def test_cache_hashing_is_streamed(bundle, monkeypatch):
    from pathlib import Path
    original = Path.read_bytes
    def read_bytes(path):
        if path.name in ('software', 'cache'):
            pytest.fail('Large reference resources must be hashed incrementally.')
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', read_bytes)
    assert run(bundle)['cases'][0]['outcomes']['parsing'] == 'parsed'


def test_command_assembly_must_match(bundle):
    bundle[1]['cases'][0]['command'][-1] = 'GRCh37'
    with pytest.raises(ValueError, match='assembly'):
        run(bundle)
