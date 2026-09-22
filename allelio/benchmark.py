"""Versioned synthetic developmental challenges with stage-specific accounting."""
import json
import hashlib
import re
from collections import Counter
from pathlib import Path
from allelio.database.store import AllelioDB
from allelio.evidence import write_evidence_export
from allelio.runs import record_run, checksum

STAGES=('parsing','identifier_recovery','identity_matching','source_selection','reporting')


def local_file(root,name):
    if not isinstance(name,str): raise ValueError('Bundle paths must be strings.')
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()): raise ValueError('Bundle resource escapes its directory.')
    if not path.is_file(): raise ValueError('Bundle resource is missing: '+name)
    return path


def observations(evidence):
    counts=evidence['coverage']['counts']; recovery=evidence['coverage'].get('probe_recovery_counts',{})
    candidates=evidence['matching']['candidates']; findings=evidence['findings']
    uncertain=any(c['decision']=='unresolved' and c['stage'] in ('identity','allele') for c in candidates)
    conflict=bool(counts.get('conflicting_input'))
    excluded=bool(counts.get('failed_filter') or counts.get('reference_or_no_applicable_annotation'))
    identity=('conflicting' if conflict else 'abstained' if uncertain else 'excluded' if excluded else
              'matched' if any(c['decision']=='retained' and c['source']=='clinvar' for c in candidates) else 'unsupported')
    return {'parsing':'parsed' if evidence['inputs'] else 'excluded',
            'identifier_recovery':('recovered' if recovery.get('recovered') else 'conflicting' if recovery.get('conflicting') else
                                   'abstained' if recovery.get('unresolved') else 'unsupported' if counts.get('unsupported_identifier') else 'not_applicable'),
            'identity_matching':identity,
            'source_selection':('abstained' if identity=='abstained' else 'selected' if findings else 'excluded'),
            'reporting':'reported' if findings else 'excluded'}


def at(document,path):
    value=document
    try:
        for key in path.split('/'):
            value=value[int(key)] if isinstance(value,list) else value[key]
        return value
    except (KeyError,IndexError,ValueError,TypeError): return None


def run_benchmark(bundle_path,output):
    bundle_path=Path(bundle_path);root=bundle_path.parent
    bundle_bytes=bundle_path.read_bytes()
    bundle=json.loads(bundle_bytes)
    if bundle.get('schema')!='allelio-challenges/1' or bundle.get('data_kind')!='synthetic' or not bundle.get('license'):
        raise ValueError('Benchmark requires a versioned, licensed synthetic challenge bundle.')
    cases=bundle.get('cases',[])
    if not cases or len({c['id'] for c in cases})!=len(cases): raise ValueError('Challenge IDs must be unique.')
    for case in cases:
        if not re.fullmatch(r'[a-z0-9_-]+',case['id']) or set(case['expected'])!=set(STAGES):
            raise ValueError('Every challenge requires a safe ID and expectations for all stages.')
    output=Path(output)
    if output.exists(): raise ValueError('Use a new output directory to preserve prior benchmark runs.')
    output.mkdir(parents=True)
    db_path=output/'references.db'; db=AllelioDB(str(db_path));db.initialize()
    refs=json.loads(local_file(root,bundle['references']).read_text())
    for source in ('clinvar','gwas','gnomad','clingen','clinpgx'):
        records=refs.get(source,[])
        if records: getattr(db,'insert_'+source+'_batch')(records)
        db.set_metadata(source+'_release',bundle['version'] if records else 'unavailable')
    db.close()
    rows=[];totals={stage:Counter() for stage in STAGES}
    for case in cases:
        source=local_file(root,case['input']);mapping=local_file(root,case['mapping']) if case.get('mapping') else None
        manifest,evidence,_=record_run(source,db_path,options={'detailed_trace':True},probe_map=mapping)
        directory=output/case['id'];directory.mkdir()
        write_evidence_export(manifest,directory/'run.json');write_evidence_export(evidence,directory/'evidence.json')
        actual=observations(evidence);checks={}
        for stage in STAGES:
            expected=case['expected'][stage]
            extra=[{'path':p,'expected':v,'actual':at(evidence,p)} for p,v in case.get('checks',{}).get(stage,{}).items()]
            matched=actual[stage]==expected and all(c['actual']==c['expected'] for c in extra)
            checks[stage]={'expected':expected,'actual':actual[stage],'passed':matched,'checks':extra}
            totals[stage]['opportunities']+=1;totals[stage]['contract_matches']+=int(matched)
            totals[stage][actual[stage]]+=1
            totals[stage]['incorrect_attributions']+=int(not matched and actual[stage] in ('matched','selected','recovered','reported'))
        rows.append({'id':case['id'],'input_sha256':manifest['input']['sha256'],
                     'references_sha256':manifest['references']['logical_sha256'],
                     'run_manifest':case['id']+'/run.json','manifest_sha256':checksum(directory/'run.json'),
                     'outcomes':actual,'checks':checks})
    report={'schema':'allelio-benchmark/1','tool':{'name':'Allelio','version':manifest['software']['version']},
            'bundle_version':bundle['version'],'bundle_sha256':hashlib.sha256(bundle_bytes).hexdigest(),
            'data_kind':'synthetic','source_versions':manifest['references']['sources'],
            'stages':{s:dict(c) for s,c in totals.items()},'cases':rows,
            'passed':all(v['passed'] for row in rows for v in row['checks'].values()),
            'limitations':['Denominators are stage-case opportunities, not patients or clinical sensitivity.',
                          'A correct exclusion or abstention is a contract match, not a successful annotation.',
                          'Developmental source-lookup agreement is not independent clinical validation.']}
    write_evidence_export(report,output/'benchmark.json')
    return report


def compare_benchmarks(left,right):
    for report in (left,right):
        if report.get('schema')!='allelio-benchmark/1' or not report.get('tool',{}).get('version'):
            raise ValueError('Comparison needs versioned benchmark exports from both tools.')
        cases=report.get('cases')
        if not isinstance(cases,list) or len({r.get('id') for r in cases})!=len(cases):
            raise ValueError('Comparison cases must have unique IDs.')
        allowed={'parsing':{'parsed','excluded'},'identifier_recovery':{'recovered','conflicting','abstained','unsupported','not_applicable'},
                 'identity_matching':{'conflicting','abstained','excluded','matched','unsupported'},
                 'source_selection':{'abstained','selected','excluded'},'reporting':{'reported','excluded'}}
        for row in cases:
            if any(not re.fullmatch(r'[0-9a-f]{64}',str(row.get(k,''))) for k in ('input_sha256','references_sha256')):
                raise ValueError('Comparison requires explicit input and reference SHA-256 fingerprints.')
            if set(row.get('outcomes',{}))!=set(STAGES) or any(row['outcomes'][s] not in allowed[s] | {'unsupported'} for s in STAGES):
                raise ValueError('Comparison outcomes must use supported stage definitions.')
    other={r['id']:r for r in right['cases']};paired=[];excluded=[]
    for row in left['cases']:
        match=other.pop(row['id'],None)
        if not match: excluded.append({'id':row['id'],'reason':'absent_in_other_tool'});continue
        if any(row[k]!=match.get(k) for k in ('input_sha256','references_sha256')):
            excluded.append({'id':row['id'],'reason':'input_or_reference_not_aligned'});continue
        for stage in STAGES:
            a,b=row['outcomes'].get(stage),match['outcomes'].get(stage)
            if a in (None,'unsupported','not_applicable') or b in (None,'unsupported','not_applicable'):
                excluded.append({'id':row['id'],'stage':stage,'reason':'not_shared_supported_scope'})
            else: paired.append({'id':row['id'],'stage':stage,'left':a,'right':b,'agreement':a==b})
    excluded.extend({'id':key,'reason':'absent_in_primary_tool'} for key in other)
    stages = {stage: {'paired_opportunities': sum(p['stage'] == stage for p in paired),
                      'agreements': sum(p['stage'] == stage and p['agreement'] for p in paired),
                      'excluded_opportunities': sum(e.get('stage') == stage or 'stage' not in e for e in excluded)}
              for stage in STAGES}
    return {'schema':'allelio-benchmark-comparison/1','tools':[left['tool'],right['tool']],
            'stages': stages,
            'paired_opportunities':len(paired),'agreements':sum(p['agreement'] for p in paired),
            'pairs':paired,'excluded':excluded,'limitation':'Aligned software comparison only; not clinical validation.'}
