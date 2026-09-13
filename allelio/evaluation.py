"""Local frozen-evidence explanation experiments and blinded human-rating support."""
import asyncio
import itertools
import json
import random
import secrets
from collections import Counter
from dataclasses import fields
from pathlib import Path

from allelio.analysis import lookup as types
from allelio.analysis.inheritance import InheritanceResolution, ConditionRef, ClinGenEntry
from allelio.ai.engine import AIEngine, REFUSED
from allelio.ai.prompts import build_variant_prompt
from allelio.benchmark import local_file
from allelio.evidence import write_evidence_export
from allelio.runs import checksum, annotation_checksum, code_identity, runtime_identity, explanation_provenance, validate_manifest
from allelio.schema import validate_evidence
import hashlib

RUBRIC=('factual_support','unsupported_certainty','material_omissions','severity','uncertainty_communication','readability')


def construct(cls,row):
    return cls(**{f.name:row[f.name] for f in fields(cls) if f.name in row})


def resolution(row):
    if row is None:return None
    value=dict(row)
    value['matched']=[construct(ClinGenEntry,r) for r in row.get('matched',[])]
    value['conditions']=[construct(ConditionRef,r) for r in row.get('conditions',[])]
    return construct(InheritanceResolution,value)


def frozen_finding(row):
    value=dict(row)
    for field,cls in [('clinvar_entries',types.ClinVarEntry),('gwas_entries',types.GWASEntry),
                      ('gnomad_entries',types.GnomADEntry),('pgx_entries',types.PGxEntry),('clingen_entries',ClinGenEntry)]:
        values=[]
        for record in row.get(field,[]):
            record=dict(record)
            if field=='clinvar_entries':record['inheritance']=resolution(record.get('inheritance'))
            values.append(construct(cls,record))
        value[field]=values
    value['gnomad_entry']=construct(types.GnomADEntry,row['gnomad_entry']) if row.get('gnomad_entry') else None
    value['inheritance_resolution']=resolution(row.get('inheritance_resolution'))
    return construct(types.VariantResult,value)


def load_cases(bundle_path):
    path=Path(bundle_path);bundle_bytes=path.read_bytes();bundle=json.loads(bundle_bytes);root=path.parent
    bundle['_sha256']=hashlib.sha256(bundle_bytes).hexdigest()
    if bundle.get('schema')!='allelio-evaluation/1' or bundle.get('split')!='evaluation':
        raise ValueError('A separate versioned evaluation split is required.')
    if bundle.get('data_kind') not in ('synthetic','external') or not bundle.get('reuse_rights'):
        raise ValueError('Document data provenance and reuse rights before evaluation.')
    if bundle['data_kind']=='external':
        if not bundle.get('provenance') or not bundle.get('rights_document'):
            raise ValueError('External material requires provenance and a local reuse-rights document.')
        local_file(root,bundle['rights_document'])
    result=[];seen=set()
    for case in bundle.get('cases',[]):
        if not isinstance(case.get('id'),str) or case['id'] in seen:raise ValueError('Unique evaluation case IDs required.')
        seen.add(case['id'])
        evidence_path=local_file(root,case['evidence']);manifest_path=local_file(root,case['run_manifest'])
        evidence_bytes=evidence_path.read_bytes();manifest_bytes=manifest_path.read_bytes()
        evidence=json.loads(evidence_bytes);manifest=json.loads(manifest_bytes)
        validate_manifest(manifest)
        errors=validate_evidence(evidence)
        if errors:raise ValueError('Frozen evidence is invalid: '+errors[0])
        if annotation_checksum(evidence)!=manifest['annotation_sha256']:
            raise ValueError('Frozen evidence does not match its run manifest.')
        rows=[r for r in evidence['findings'] if r['finding_id']==case['finding_id']]
        if len(rows)!=1:raise ValueError('Evaluation case must reference exactly one frozen finding.')
        result.append({'id':case['id'],'evidence':rows[0],'finding':frozen_finding(rows[0]),
                       'evidence_sha256':hashlib.sha256(evidence_bytes).hexdigest(),'run_manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest()})
    if not result:raise ValueError('Evaluation bundle has no cases.')
    return bundle,result


def generate_evaluation(bundle_path, output, models=(), repetitions=1):
    if type(repetitions) is not int or not 1<=repetitions<=10:raise ValueError('Use 1–10 model repetitions.')
    if len(models)>8 or len(set(models))!=len(models):raise ValueError('Use at most eight distinct model arms.')
    bundle,cases=load_cases(bundle_path)
    output=Path(output)
    if output.exists():raise ValueError('Use a new output directory to preserve prior evaluations.')
    output.mkdir(parents=True)
    records=[];arms=[]
    for case in cases:
        text=AIEngine._fallback_explanation(None,case['finding'],reason='Reference annotation')
        records.append({'case_id':case['id'],'arm':'template','repeat':1,'text':text,'status':'generated'})
    arms.append({'arm':'template','kind':'deterministic_template','repetitions':1})
    async def generate():
        for index,model in enumerate(models,1):
            engine=AIEngine(model=model);configured=engine.model
            await engine.check_connection()
            arm='model-'+str(index);written={}
            for case in cases:
                for repetition in range(1,repetitions+1):
                    if engine.status==REFUSED:
                        records.append({'case_id':case['id'],'arm':arm,'repeat':repetition,'status':'refused','text':None});continue
                    explanation=await engine.explain(case['finding'])
                    written[case['id']+'/'+str(repetition)]=explanation
                    # A model failure is retained as a failed arm, not silently
                    # scored as if a model generated the fallback template.
                    records.append({'case_id':case['id'],'arm':arm,'repeat':repetition,
                                    'status':'generated' if explanation.model else 'fallback',
                                    'text':explanation.text})
            provenance=explanation_provenance(engine,True,len(cases),written,configured)
            provenance['generation']['repetitions']=repetitions
            arms.append({'arm':arm,'repetitions':repetitions,'provenance':provenance})
    if models:asyncio.run(generate())
    lookup={c['id']:c for c in cases};blinded=[];key=[]
    for row in records:
        if row['status']!='generated':continue
        blind_id=secrets.token_hex(12)
        blinded.append({'case_id':blind_id,'evidence':lookup[row['case_id']]['evidence'],'text':row['text']})
        key.append({'case_id':blind_id,'source_case':row['case_id'],'arm':row['arm'],'repeat':row['repeat']})
    random.SystemRandom().shuffle(blinded)
    public={'schema':'allelio-blinded-cases/1','rubric':list(RUBRIC),'cases':blinded,
            'limitations':['Arm labels are hidden, but writing style can reveal a generator.',
                          'These are software-generated evaluation materials, not completed independent review.']}
    private={'schema':'allelio-evaluation-run/1','bundle_sha256':bundle['_sha256'],'data_kind':bundle['data_kind'],
             'reuse_rights':bundle['reuse_rights'],'software':code_identity(),'runtime':runtime_identity(),
             'arms':arms,'outputs':records,'blinding_key':key,
             'cases':[{'id':c['id'],'evidence_sha256':c['evidence_sha256'],'run_manifest_sha256':c['run_manifest_sha256'],
                       'prompt_sha256':hashlib.sha256(build_variant_prompt(c['finding']).encode()).hexdigest()} for c in cases],
             'failed_outputs':sum(r['status']!='generated' for r in records)}
    write_evidence_export(public,output/'blinded-cases.json')
    write_evidence_export(private,output/'private-run.json')
    write_evidence_export({'schema':'allelio-ratings/1','blinded_sha256':checksum(output/'blinded-cases.json'),
        'raters':['rater-1'],'ratings':[{'case_id':case['case_id'],'rater_id':'rater-1',
        'scores':{key:None for key in RUBRIC},'disputed':False,'comment':''} for case in blinded]},output/'ratings-template.json')
    schema=json.loads((Path(__file__).parent/'schemas'/'ratings-1.json').read_text())
    write_evidence_export(schema,output/'ratings-schema.json')
    return {'generated_cases':len(blinded),'failed_outputs':private['failed_outputs'],'outputs':len(records)}


def summarize_ratings(blinded_path,ratings_path):
    from jsonschema import Draft202012Validator
    blinded=json.loads(Path(blinded_path).read_text());ratings=json.loads(Path(ratings_path).read_text())
    schema=json.loads((Path(__file__).parent/'schemas'/'ratings-1.json').read_text())
    errors=list(Draft202012Validator(schema).iter_errors(ratings))
    if errors:raise ValueError('Invalid ratings: '+errors[0].message)
    if blinded.get('schema')!='allelio-blinded-cases/1':raise ValueError('Unsupported blinded cases schema.')
    if ratings['blinded_sha256'] != checksum(blinded_path): raise ValueError('Ratings refer to a different blinded export.')
    if not isinstance(blinded.get('cases'),list) or not blinded['cases']:
        raise ValueError('Blinded case list must not be empty.')
    case_ids={c['case_id'] for c in blinded['cases']}
    if len(case_ids)!=len(blinded['cases']):raise ValueError('Duplicate blinded case IDs.')
    raters=ratings['raters'];seen={};rows=ratings['ratings']
    for row in rows:
        pair=(row['case_id'],row['rater_id'])
        if row['case_id'] not in case_ids or row['rater_id'] not in raters or pair in seen:
            raise ValueError('Unknown case/rater or duplicate case-rater rating.')
        seen[pair]=row
    dimensions={}
    for dimension in RUBRIC:
        distribution=Counter();comparisons=agreements=0;missing=disputed=0
        for case in case_ids:
            eligible=[]
            for rater in raters:
                row=seen.get((case,rater));score=row['scores'][dimension] if row else None
                if row and row['disputed']:disputed+=1
                elif score is None:missing+=1
                else:distribution[score]+=1;eligible.append(score)
            for a,b in itertools.combinations(eligible,2):comparisons+=1;agreements+=int(a==b)
        dimensions[dimension]={'expected_ratings':len(case_ids)*len(raters),'scored':sum(distribution.values()),
                               'missing':missing,'disputed':disputed,'distribution':dict(distribution),
                               'pairwise_comparisons':comparisons,'exact_agreements':agreements,
                               'exact_agreement_fraction':agreements/comparisons if comparisons else None}
    return {'schema':'allelio-rating-summary/1','cases':len(case_ids),'raters':len(raters),
            'expected_rows':len(case_ids)*len(raters),'received_rows':len(rows),
            'missing_rows':len(case_ids)*len(raters)-len(rows),'dimensions':dimensions,
            'ratings':rows,'blinded_sha256':checksum(blinded_path),'ratings_sha256':checksum(ratings_path),
            'limitations':['Missing and disputed ratings are retained and excluded from agreement denominators.',
                          'Pairwise exact agreement is descriptive, not chance-corrected or expert judgment.',
                          'Synthetic ratings test software; they do not establish independent or clinical validation.']}
