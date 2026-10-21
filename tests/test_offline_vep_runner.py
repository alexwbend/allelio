"""Invented execution receipts only; public CI does not provision/run VEP."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('vep_smoke_runner',ROOT/'scripts/run_offline_vep_smoke.py')
runner=importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)


@pytest.mark.parametrize('fault',[None,'network','writable_cache','foreign_mount','nonzero','timeout'])
def test_execution_policy_and_nonzero_exit_cannot_be_scope_exclusions(tmp_path,monkeypatch,fault):
    source=tmp_path/'synthetic.vcf'; source.write_text('Invented input only\n')
    output=tmp_path/'case'; output.mkdir()
    protocol={'vep_arguments':['--offline','--cache','--json','--assembly','GRCh38'],
              'image_id':'synthetic-image','image_config_digest':'synthetic-config'}
    calls=[]; inspections=[]
    before={'HostConfig':{'NetworkMode':'bridge' if fault=='network' else 'none','ReadonlyRootfs':True},
            'Mounts':[{'Type':'bind' if fault=='foreign_mount' else 'volume','Name':runner.VOLUME,
                       'Destination':'/cache','RW':fault=='writable_cache'}],
            'Config':{'Image':runner.IMAGE},'Image':'synthetic-config'}
    def docker(context,args,**kwargs):
        calls.append(args)
        if args[0]=='create':return SimpleNamespace(stdout=b'synthetic-container\n')
        if args[0]=='inspect':
            inspections.append(True)
            return SimpleNamespace(stdout=json.dumps([before if len(inspections)==1 else
                {'State':{'ExitCode':1 if fault=='nonzero' else 0}}]).encode())
        if args[0]=='rm':return SimpleNamespace(stdout=b'')
        pytest.fail('Unexpected container operation')
    monkeypatch.setattr(runner,'docker',docker)
    def execute(args,**kwargs):
        assert args[3:]==['start','--attach','--interactive','synthetic-container']
        assert kwargs['stdin'].read()==source.read_bytes()
        if fault=='timeout':raise subprocess.TimeoutExpired(args,120)
        kwargs['stdout'].write(b'{"input":"invented"}\n')
        return SimpleNamespace(returncode=1 if fault=='nonzero' else 0)
    monkeypatch.setattr(runner.subprocess,'run',execute)
    if fault:
        with pytest.raises((ValueError,subprocess.TimeoutExpired)):
            runner.execute_case('unit-test',source,output,protocol)
    else:
        command,receipt=runner.execute_case('unit-test',source,output,protocol)
        assert command[command.index('--network')+1]=='none'
        assert '--read-only' in command and 'readonly' in command[command.index('--mount')+1]
        assert receipt['container_exit_code']==0 and receipt['cache_readonly']
    assert calls[-1]==['rm','--force','synthetic-container']


def test_tracked_output_is_rejected_before_any_runtime_call(tmp_path,monkeypatch):
    root=tmp_path/'checkout'; root.mkdir(); (root/'.git').mkdir()
    monkeypatch.setattr(runner,'docker',lambda *a,**k:pytest.fail('No runtime call before preflight'))
    with pytest.raises(ValueError):runner.outside(root/'output')


def test_public_fixture_expects_no_annotation_truth(tmp_path):
    from allelio.benchmark import run_benchmark
    result=run_benchmark(ROOT/'examples/vep-parsing/bundle.json',tmp_path/'primary')
    assert result['passed'] and len(result['cases'])==11
    assert result['stages']['reporting'].get('reported',0)==0
    assert result['stages']['parsing']['parsed']==10


@pytest.mark.parametrize('guard',['source','existing_volume'])
def test_preparation_guards_survive_optimized_python(tmp_path,guard):
    resources=tmp_path/'resources'; resources.mkdir()
    (resources/'ensembl-vep-f479099e.tar.gz').write_bytes(b'invented invalid archive')
    (resources/'vep-116.3-arm64.tar').write_bytes(b'invented image')
    script=('import sys; from types import SimpleNamespace; '
            'sys.path.insert(0,sys.argv[1]); import prepare_vep_smoke_resources as p; '
            'p.subprocess.run=lambda *a,**k:SimpleNamespace(returncode='+('0' if guard=='existing_volume' else '1')+'); '
            '\ntry:p.prepare(sys.argv[2],"synthetic")\nexcept ValueError:print("REJECTED")\nelse:print("UNSAFE")')
    result=subprocess.run([sys.executable,'-O','-c',script,str(ROOT/'scripts'),str(resources)],capture_output=True,text=True)
    assert result.returncode==0 and result.stdout.strip()=='REJECTED'
    assert not (resources/'cache-84-GRCh38.tar.gz').exists()


def test_preparer_rejects_git_storage_before_services_or_writes(tmp_path,monkeypatch):
    import prepare_vep_smoke_resources as prep
    root=tmp_path/'checkout'; root.mkdir(); (root/'.git').mkdir()
    monkeypatch.setattr(prep.subprocess,'run',lambda *a,**k:pytest.fail('No Docker operation for a tracked resource directory'))
    with pytest.raises(ValueError):prep.prepare(root,'synthetic')


@pytest.mark.parametrize('mutation',[None,'receipt','primary_evidence','imported_log'])
def test_full_local_adapter_run_and_retained_artifact_mutation(tmp_path,monkeypatch,mutation):
    import copy
    resources=tmp_path/'resources'; resources.mkdir()
    protocol=json.loads(runner.PROTOCOL.read_text())
    metadata={'image':runner.IMAGE,'resources':copy.deepcopy(protocol['resources'])}
    for r in metadata['resources']:
        (resources/r['path']).write_bytes(('synthetic '+r['kind']).encode()); r['sha256']=runner.sha(resources/r['path'])
    inventory={'homo_sapiens/84_GRCh38/'+name:digest for name,digest in protocol['fasta_copy_sha256'].items()}
    (resources/'cache-inventory.json').write_text(json.dumps(inventory))
    (resources/'runtime.json').write_text(json.dumps(metadata))
    protocol.update(runtime_metadata_sha256=runner.sha(resources/'runtime.json'),resources=metadata['resources'],
                    cache_inventory_sha256=runner.sha(resources/'cache-inventory.json'))
    path=tmp_path/'protocol.json'; path.write_text(json.dumps(protocol)); output=tmp_path/'output'
    monkeypatch.setattr(runner,'PROTOCOL',path)
    monkeypatch.setattr(runner,'verify_image_archive',lambda p:protocol['image_config_digest'])
    monkeypatch.setattr(runner,'cache_inventory',lambda ctx:inventory)
    def execute(context,source,directory,p):
        rows=[line for line in source.read_text().splitlines() if line and not line.startswith('#')]
        (directory/'vep.jsonl').write_text(''.join(json.dumps({'input':r})+'\n' for r in rows))
        (directory/'vep.log').write_text('Invented unit fixture; VEP not executed.\n')
        receipt={'unit_fixture':True}; runner.write_evidence_export(receipt,directory/'execution.json')
        if directory.name=='multiallelic':
            if mutation=='receipt':(output/'diploid_het/execution.json').write_text('{}')
            if mutation=='primary_evidence':(output/'allelio/diploid_het/evidence.json').write_text('{}')
        return ['vep']+p['vep_arguments'],receipt
    monkeypatch.setattr(runner,'execute_case',execute)
    if mutation=='imported_log':
        compare=runner.compare_benchmarks
        def changed(*args):
            result=compare(*args); (output/'imported/diploid_het/vep.log').write_text('changed'); return result
        monkeypatch.setattr(runner,'compare_benchmarks',changed)
    if mutation:
        with pytest.raises(ValueError):runner.run(resources,output,'synthetic')
        assert not (output/'report.json').exists() and (output/'INCOMPLETE').exists()
    else:
        report=runner.run(resources,output,'synthetic')
        assert report['comparison']['agreements']==report['comparison']['paired_opportunities']==6
        assert sum(c['parsing_counts']['input_records'] for c in report['cases'] if c['parsing_counts'])==7
        assert sum(s['excluded_opportunities'] for s in report['comparison']['stages'].values())==49
        assert 'diploid_het/execution.json' in report['supporting_artifact_hashes']


def test_fasta_lock_setup_keeps_original_cache_readonly():
    protocol=json.loads(runner.PROTOCOL.read_text())
    assert protocol['vep_arguments'][-2:]==['--fasta','/tmp/test.fa']
    assert set(protocol['fasta_copy_sha256'])=={'test.fa','test.fa.fai'}
    assert 'cp /cache/homo_sapiens/84_GRCh38/test.fa' in runner.ENTRY_COMMAND[2]
    assert 'exec vep "$@"' in runner.ENTRY_COMMAND[2]
