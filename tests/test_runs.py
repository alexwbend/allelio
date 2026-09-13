import copy
import json
import socket
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from allelio import runs
from allelio.cli import allelio
from allelio.database.store import AllelioDB


@pytest.fixture
def bundle(tmp_path):
    source = tmp_path / 'synthetic.txt'
    source.write_text('rs1\t1\t100\tAG\nrs2\t2\t200\tCC\n')
    database = tmp_path / 'references.db'
    db = AllelioDB(str(database)); db.initialize()
    db.insert_clinvar_batch([dict(rsid='rs1', ref_allele='G', alt_allele='A',
        chromosome='1', position_vcf=100, assembly='GRCh38', allele_id='1',
        clinical_significance='Pathogenic', gene='SYNTHETIC', conditions='Synthetic condition')])
    db.set_metadata('clinvar_url', 'file:///private/patient?credential=secret')
    db.close()
    return source, database


def test_offline_replay_and_privacy(bundle, monkeypatch):
    def deny(*args, **kwargs): raise AssertionError('Network attempt')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket, 'getaddrinfo', deny)
    manifest, evidence, _ = runs.record_run(*bundle)
    runs.validate_manifest(manifest)
    result, replayed = runs.replay_run(manifest, *bundle)
    assert result['annotation_replayed'] and not result['explanations_replayed']
    assert runs.annotation_checksum(evidence) == runs.annotation_checksum(replayed)
    serialized = json.dumps(manifest)
    for private in (str(bundle[0]), str(bundle[1]), 'credential', 'secret', 'rs1', 'SYNTHETIC'):
        assert private not in serialized
    assert manifest['references']['sources']['clinvar']['sha256'] is None
    assert manifest['explanations']['model_digest'] is None


def test_database_change_without_version_change_is_rejected(bundle):
    manifest, _, _ = runs.record_run(*bundle)
    db = sqlite3.connect(str(bundle[1]))
    db.execute("UPDATE clinvar SET gene='CHANGED'"); db.commit(); db.close()
    with pytest.raises(ValueError, match='Reference contents'):
        runs.replay_run(manifest, *bundle)


def test_wal_change_is_detected_and_checkpoint_does_not_change_identity(bundle):
    db = AllelioDB(str(bundle[1]))
    db.set_metadata('test', 'before')
    before, _, _ = runs.record_run(*bundle)
    db.conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    assert runs.replay_run(before, *bundle)[0]['verified']
    db.set_metadata('test', 'after')
    with pytest.raises(ValueError, match='Reference contents'):
        runs.replay_run(before, *bundle)
    db.close()


def test_input_code_and_missing_reference_fail_clearly(bundle, monkeypatch):
    manifest, _, _ = runs.record_run(*bundle)
    changed = copy.deepcopy(manifest); changed['software']['version'] = 'other'
    with pytest.raises(ValueError, match='package contents'):
        runs.replay_run(changed, *bundle)
    with pytest.raises(ValueError, match='missing'):
        runs.replay_run(manifest, bundle[0], bundle[1].with_name('missing.db'))
    bundle[0].write_text('rs1\t1\t100\tAA\n')
    with pytest.raises(ValueError, match='Input checksum'):
        runs.replay_run(manifest, *bundle)


def test_output_hash_and_options_cannot_silently_change(bundle):
    manifest, _, _ = runs.record_run(*bundle)
    changed = copy.deepcopy(manifest); changed['annotation_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='Annotation differs'):
        runs.replay_run(changed, *bundle)
    assert runs.replay_run(changed, *bundle, verify_only=True)[0]['annotation_replayed'] is False
    changed['options']['invented'] = True
    with pytest.raises(ValueError, match='Invalid run manifest'):
        runs.replay_run(changed, *bundle)


def test_runtime_difference_is_explicit(bundle):
    manifest, _, _ = runs.record_run(*bundle)
    manifest['runtime']['python'] = '0.0.0'
    result, _ = runs.replay_run(manifest, *bundle)
    assert result['runtime_differences']['python']['recorded'] == '0.0.0'


def test_input_mutation_during_run_is_rejected(bundle, monkeypatch):
    original = runs.annotation
    def mutate(file, db, options):
        answer = original(file, db, options)
        Path(file).write_text('rs1\t1\t100\tAA\n')
        return answer
    monkeypatch.setattr(runs, 'annotation', mutate)
    with pytest.raises(ValueError, match='Input changed during'):
        runs.record_run(*bundle)


def test_cli_records_replays_and_protects_paths(bundle, tmp_path):
    source, db = bundle; manifest = tmp_path / 'run.json'; evidence = tmp_path / 'evidence.json'
    runner = CliRunner()
    result = runner.invoke(allelio, ['record-run', str(source), '--database', str(db), '--manifest', str(manifest), '--evidence-output', str(evidence)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(allelio, ['replay-run', str(manifest), '--input', str(source), '--database', str(db)])
    assert result.exit_code == 0, result.output
    for output in (str(source), str(db), str(db)+'-wal'):
        result = runner.invoke(allelio, ['record-run', str(source), '--database', str(db), '--manifest', output])
        assert result.exit_code != 0 and 'must differ' in result.output
    from allelio.schema import validate_evidence_file
    assert validate_evidence_file(str(evidence)) == []


def test_unavailable_model_and_missing_digest_stay_explicit(bundle, monkeypatch):
    from allelio.ai import engine
    from allelio.ai.attribution import Explanation
    class Unavailable:
        model = 'synthetic-model'; provider = 'Ollama'; status = 'unreachable'
        def __init__(self, model=None): pass
        async def check_connection(self): return False
        async def explain(self, result): return Explanation('Synthetic fallback', None, 'secret exception')
    monkeypatch.setattr(engine, 'AIEngine', Unavailable)
    manifest, _, _ = runs.record_run(*bundle, explain=True)
    assert manifest['explanations']['fallback_status'] == 'all'
    assert manifest['explanations']['model_digest'] is None
    assert 'secret exception' not in json.dumps(manifest)
    assert runs.replay_run(manifest, *bundle)[0]['annotation_replayed']


@pytest.mark.asyncio
async def test_available_model_digest_and_stale_digest_reset(monkeypatch):
    from allelio.ai import engine
    monkeypatch.delenv(engine.OPENAI_BASE_ENV, raising=False)
    monkeypatch.setattr(engine, 'pin_to_loopback', lambda url, setting: url)
    client = engine.AIEngine(model='synthetic')
    class Listing:
        async def list(self): return {'models': [{'name': 'synthetic:latest', 'digest': 'a'*64}]}
    client.client = Listing()
    assert await client.check_connection()
    assert client.model_digest == 'a'*64
    class Missing:
        async def list(self): raise ConnectionError('offline')
    client.client = Missing()
    await client.check_connection()
    assert client.model_digest is None
    client.model_digest = 'a'*64
    client.client = None
    await client.check_connection()
    assert client.model_digest is None


def test_symlink_database_sidecar_is_protected(bundle, tmp_path):
    source, db = bundle
    alias = tmp_path / 'alias.db'; alias.symlink_to(db)
    result = CliRunner().invoke(allelio, ['record-run', str(source), '--database', str(alias),
        '--manifest', str(db)+'-wal'])
    assert result.exit_code != 0 and 'must differ' in result.output


def test_all_recorded_options_replay(bundle):
    manifest, evidence, _ = runs.record_run(*bundle, options={
        'include_benign': True, 'include_reference': True, 'frequency_adjustment': False,
        'traits_only': True, 'detailed_trace': True, 'pgx_min_level': '3'})
    assert runs.replay_run(manifest, *bundle)[0]['annotation_replayed']
    assert evidence['configuration']['pgx_min_level'] == '3'


def test_read_snapshot_survives_concurrent_reference_update(bundle):
    with runs.references(bundle[1]) as reader:
        before = runs.reference_identity(reader)
        writer = sqlite3.connect(str(bundle[1]))
        writer.execute("UPDATE clinvar SET gene='CONCURRENT'"); writer.commit(); writer.close()
        assert runs.reference_identity(reader) == before
    with runs.references(bundle[1]) as reader:
        assert runs.reference_identity(reader) != before
