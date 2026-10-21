#!/usr/bin/env python3
"""Execute a frozen synthetic parsing smoke experiment with real offline VEP."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]
from allelio.benchmark import INTERNAL_VEP_SCHEMA, compare_benchmarks, run_benchmark
from allelio.evidence import write_evidence_export
from allelio.reference_evaluation import public_runtime
from allelio.runs import code_identity, annotation_checksum, references, reference_identity
from allelio.schema import validate_evidence
from allelio.vep import import_vep
from prepare_vep_smoke_resources import IMAGE, VOLUME, cache_inventory, docker, sha, verify_image_archive

PROTOCOL = ROOT/'data/evaluation/vep-parsing-v1.protocol.json'


def require(condition):
    if not condition: raise ValueError('Frozen offline VEP experiment contract failed.')


def outside(path):
    path = Path(path).resolve()
    require(not any((p/'.git').exists() for p in (path,*path.parents)))
    return path


def execute_case(context, source, directory, protocol):
    """No host mounts: invented VCF bytes enter stdin; only cache is mounted."""
    args = protocol['vep_arguments']
    create = ['create','--interactive','--network','none','--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m',
              '--cap-drop','ALL','--security-opt','no-new-privileges','--mount',
              'type=volume,src='+VOLUME+',dst=/cache,readonly',IMAGE,'vep'] + args
    container = docker(context,create).stdout.decode().strip()
    try:
        before = json.loads(docker(context,['inspect',container]).stdout)[0]
        policy = before['HostConfig']; mounts = before['Mounts']
        require(policy['NetworkMode']=='none' and policy['ReadonlyRootfs'] is True
                and len(mounts)==1 and mounts[0]['Type']=='volume' and mounts[0]['Name']==VOLUME
                and mounts[0]['Destination']=='/cache' and mounts[0]['RW'] is False
                and before['Config']['Image']==IMAGE
                and before['Image'] in (protocol['image_id'],protocol['image_config_digest']))
        with source.open('rb') as incoming, (directory/'vep.jsonl').open('xb') as outgoing, (directory/'vep.log').open('xb') as log:
            result = subprocess.run(['docker','--context',context,'start','--attach','--interactive',container],
                                    stdin=incoming,stdout=outgoing,stderr=log,timeout=120)
        after = json.loads(docker(context,['inspect',container]).stdout)[0]
        receipt = {'create_arguments':create,'network_mode':policy['NetworkMode'],'root_readonly':True,
            'cache_readonly':True,'image_config_or_manifest_digest':before['Image'],
            'client_exit_code':result.returncode,'container_exit_code':after['State']['ExitCode']}
        write_evidence_export(receipt,directory/'execution.json')
        require(result.returncode==after['State']['ExitCode']==0)
        return create, receipt
    finally:
        docker(context,['rm','--force',container])


def run(resources, output, context):
    resources,output = outside(resources),outside(output)
    require(not output.exists())
    protocol_bytes = PROTOCOL.read_bytes(); protocol = json.loads(protocol_bytes)
    require(protocol['schema']=='allelio-offline-vep-smoke/1' and protocol['data_kind']=='synthetic'
            and protocol['split']=='development' and protocol['image']==IMAGE
            and protocol['compared_stages']==['parsing'] and protocol['independent_validation'] is False)
    fixture = ROOT/'examples/vep-parsing'
    require(all(sha(fixture/name)==digest for name,digest in protocol['inputs'].items()))
    require(sha(resources/'runtime.json')==protocol['runtime_metadata_sha256'])
    runtime = json.loads((resources/'runtime.json').read_text())
    require(runtime['image']==IMAGE and runtime['resources']==protocol['resources'])
    require(all(sha(resources/r['path'])==r['sha256'] for r in runtime['resources']))
    require(verify_image_archive(resources/'vep-116.3-arm64.tar')==protocol['image_config_digest'])
    inventory = json.loads((resources/'cache-inventory.json').read_text())
    require(sha(resources/'cache-inventory.json')==protocol['cache_inventory_sha256'])
    software = code_identity(); runner_hash = sha(__file__)
    helper = Path(__file__).with_name('prepare_vep_smoke_resources.py'); helper_hash = sha(helper)
    output.mkdir(parents=True,mode=0o700); output.chmod(0o700)
    (output/'INCOMPLETE').write_text('Retain failed artifacts; never reuse this output directory.\n')
    retained = {}
    def retain(data,name):
        encoded = (json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode()
        (output/name).parent.mkdir(parents=True,exist_ok=True)
        (output/name).write_bytes(encoded); retained[name] = hashlib.sha256(encoded).hexdigest()
    def track_json(data,name):
        encoded = (json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode()
        digest = hashlib.sha256(encoded).hexdigest()
        require(sha(output/name)==digest); retained[name]=digest
    (output/'protocol.json').write_bytes(protocol_bytes)
    retained['protocol.json'] = hashlib.sha256(protocol_bytes).hexdigest()
    try:
        (output/'resources').mkdir()
        for r in runtime['resources']: os.link(resources/r['path'],output/'resources'/r['path'])
        shutil.copytree(fixture,output/'inputs')
        require(all(sha(output/'inputs'/name)==digest for name,digest in protocol['inputs'].items()))
        primary = run_benchmark(output/'inputs/bundle.json',output/'allelio')
        require(primary['passed'])
        track_json(primary,'allelio/benchmark.json')
        db_hashes = {c['references_sha256'] for c in primary['cases']}; require(len(db_hashes)==1)
        for case in primary['cases']:
            manifest_name='allelio/'+case['run_manifest']
            require(sha(output/manifest_name)==case['manifest_sha256'])
            retained[manifest_name]=case['manifest_sha256']
            manifest=json.loads((output/manifest_name).read_bytes())
            evidence_name='allelio/'+case['id']+'/evidence.json'
            evidence_bytes=(output/evidence_name).read_bytes(); evidence=json.loads(evidence_bytes)
            require(annotation_checksum(evidence)==manifest['annotation_sha256'] and not validate_evidence(evidence))
            retained[evidence_name]=hashlib.sha256(evidence_bytes).hexdigest()
        with references(output/'allelio/references.db') as db:
            require(reference_identity(db)['logical_sha256']==next(iter(db_hashes)))
        retained['allelio/references.db']=sha(output/'allelio/references.db')
        cases,receipts = [],{}
        for case in primary['cases']:
            require(cache_inventory(context)==inventory)
            directory = output/case['id']; directory.mkdir()
            source = output/'inputs'/(case['id']+'.vcf')
            command,receipt = execute_case(context,source,directory,protocol)
            receipts[case['id']] = receipt
            track_json(receipt,case['id']+'/execution.json')
            cases.append({'id':case['id'], 'input':{'path':source.relative_to(output).as_posix(),'sha256':sha(source)},
                'raw_output':{'path':case['id']+'/vep.jsonl','sha256':sha(directory/'vep.jsonl')},
                'log':{'path':case['id']+'/vep.log','sha256':sha(directory/'vep.log')},'command':command,'exit_code':0,
                'alignment':{'schema':'allelio-internal-parsing-alignment/1','scope':['parsing'],
                    'prepared_by':'Codex','internal_review':protocol['internal_review'],
                    'date':protocol['review_date'],'rationale':protocol['alignment_rationale'],
                    'independent_validation':False,'source_equivalence':False,
                    'input_sha256':case['input_sha256'],'allelio_references_sha256':case['references_sha256'],
                    'resource_sha256':[r['sha256'] for r in runtime['resources']]}})
        manifest = {'schema':INTERNAL_VEP_SCHEMA,'split':'development','data_kind':'synthetic',
            'license':'Invented inputs MIT; software Apache-2.0; upstream cache retains separate source terms.',
            'vep_version':'116.3','assembly':'GRCh38','hardware':protocol['hardware'],
            'resources':[{**r,'path':'resources/'+r['path']} for r in runtime['resources']], 'plugins':[],'cases':cases}
        retain(manifest,'import-manifest.json')
        external = import_vep(output/'import-manifest.json',output/'imported')
        track_json(external,'imported/benchmark.json')
        retained['imported/import-manifest.json']=retained['import-manifest.json']
        for case in cases:
            for key,name in (('input','input.txt'),('raw_output','vep.jsonl'),('log','vep.log')):
                path='imported/'+case['id']+'/'+name
                require(sha(output/path)==case[key]['sha256']); retained[path]=case[key]['sha256']
        comparison = compare_benchmarks(primary,external); retain(comparison,'comparison.json')
        # Recheck snapshots/resources and retained output, without publishing annotation payloads.
        require(code_identity()==software and sha(__file__)==runner_hash and sha(helper)==helper_hash
                and PROTOCOL.read_bytes()==protocol_bytes and cache_inventory(context)==inventory
                and all(sha(resources/r['path'])==r['sha256'] for r in runtime['resources'])
                and all(sha(output/'inputs'/n)==h and sha(fixture/n)==h for n,h in protocol['inputs'].items())
                and all(sha(output/n)==h for n,h in retained.items()))
        for case in cases:
            for key in ('input','raw_output','log'):
                require(sha(output/case[key]['path'])==case[key]['sha256'])
        public_cases = [{'id':c['id'],'input_sha256':c['input_sha256'],'parsing_outcome':c['outcomes']['parsing'],
                         'scope_reason':c['scope_reason'],'parsing_counts':c['parsing_counts'],
                         'vep_exit_code':0,'network_mode':'none'} for c in external['cases']]
        report = {'schema':'allelio-offline-vep-smoke-results/1','status':'complete','data_kind':'synthetic',
            'split':'development','independent_validation':False,'source_equivalence':False,
            'protocol_sha256':hashlib.sha256(protocol_bytes).hexdigest(),'runner_sha256':runner_hash,
            'resource_preparer_sha256':helper_hash,'software':software,'runtime':public_runtime(),
            'vep_version':'116.3','image':IMAGE,'cache_version':'84_GRCh38 sparse upstream test cache',
            'cache_inventory_sha256':protocol['cache_inventory_sha256'],
            'vep_resource_set_sha256':external['resource_set_sha256'],'allelio_reference_sha256':next(iter(db_hashes)),
            'cases':public_cases,'comparison':comparison,
            'original_artifact_hashes':{c['id']:{key:c[key]['sha256'] for key in ('input','raw_output','log')} for c in cases},
            'supporting_artifact_hashes':dict(retained),
            'limitations':protocol['limitations']}
        retain(report,'report.pending.json')
        (output/'INCOMPLETE').unlink(); (output/'report.pending.json').rename(output/'report.json')
        return report
    except Exception:
        with (output/'failure.log').open('a') as log: traceback.print_exc(file=log)
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--resources',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True); p.add_argument('--docker-context',required=True)
    a=p.parse_args(); os.umask(0o077)
    try: result=run(a.resources,a.output,a.docker_context)
    except Exception:
        print('Offline VEP experiment incomplete; inspect retained local diagnostics.',file=sys.stderr); sys.exit(2)
    c=result['comparison']; print('Shared parsing case agreements: %d/%d.'%(c['agreements'],c['paired_opportunities']))
    sys.exit(0 if c['agreements']==c['paired_opportunities'] else 1)
