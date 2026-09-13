import copy
import json
from pathlib import Path
import pytest
from click.testing import CliRunner
from allelio.cli import allelio
from allelio.benchmark import run_benchmark,compare_benchmarks
from allelio.evaluation import generate_evaluation,summarize_ratings,RUBRIC,load_cases

ROOT=Path(__file__).resolve().parents[1]


def test_benchmark_stages_and_scope_comparison(tmp_path):
    report=run_benchmark(ROOT/'examples/challenges/bundle.json',tmp_path/'benchmark')
    assert report['passed'] and len(report['cases'])==11
    assert report['stages']['identity_matching']['opportunities']==11
    assert report['stages']['identity_matching']['abstained']==1
    assert report['stages']['identity_matching']['incorrect_attributions']==0
    changed=copy.deepcopy(report);changed['tool']={'name':'synthetic-other','version':'1'}
    changed['cases'][0]['references_sha256']='0'*64
    comparison=compare_benchmarks(report,changed)
    assert any(r['reason']=='input_or_reference_not_aligned' for r in comparison['excluded'])
    assert comparison['paired_opportunities']>0
    assert comparison['agreements']==comparison['paired_opportunities']
    assert any(r['reason']=='not_shared_supported_scope' for r in comparison['excluded'])


def test_frozen_case_integrity_and_rights(tmp_path):
    import shutil
    target=tmp_path/'cases';shutil.copytree(ROOT/'examples/evaluation',target)
    bundle=json.loads((target/'bundle.json').read_text());bundle['data_kind']='external'
    (target/'bundle.json').write_text(json.dumps(bundle))
    with pytest.raises(ValueError,match='rights'):load_cases(target/'bundle.json')
    bundle['data_kind']='synthetic';(target/'bundle.json').write_text(json.dumps(bundle))
    evidence=json.loads((target/'evidence.json').read_text());evidence['findings'][0]['genotype']='TT'
    (target/'evidence.json').write_text(json.dumps(evidence))
    with pytest.raises(ValueError,match='does not match'):load_cases(target/'bundle.json')


def test_template_blinding_and_missing_disputed_rating_denominators(tmp_path,monkeypatch):
    import socket
    attempts=[]
    def deny(*args,**kwargs):attempts.append(args);raise AssertionError('network')
    monkeypatch.setattr(socket.socket,'connect',deny);monkeypatch.setattr(socket,'getaddrinfo',deny)
    output=tmp_path/'eval';result=generate_evaluation(ROOT/'examples/evaluation/bundle.json',output)
    assert result['generated_cases']==2 and not attempts
    blinded=json.loads((output/'blinded-cases.json').read_text())
    assert all('arm' not in row and 'model' not in row for row in blinded['cases'])
    ratings=json.loads((output/'ratings-template.json').read_text());ratings['raters']=['rater-1','rater-2']
    for row in ratings['ratings']:row['scores']={key:3 for key in RUBRIC}
    other=copy.deepcopy(ratings['ratings'][0]);other['rater_id']='rater-2';other['disputed']=True
    ratings['ratings'].append(other);rating_path=output/'ratings.json';rating_path.write_text(json.dumps(ratings))
    report=summarize_ratings(output/'blinded-cases.json',rating_path)
    assert report['expected_rows']==4 and report['received_rows']==3 and report['missing_rows']==1
    for result in report['dimensions'].values():
        assert result['scored']==2 and result['missing']==1 and result['disputed']==1
        assert result['exact_agreement_fraction'] is None
    other['disputed']=False;other['scores']['severity']=1
    ratings['ratings'][-1]=other;rating_path.write_text(json.dumps(ratings))
    report=summarize_ratings(output/'blinded-cases.json',rating_path)
    assert report['dimensions']['severity']['exact_agreement_fraction']==0
    assert report['dimensions']['factual_support']['exact_agreement_fraction']==1
    ratings['ratings'].append(other);rating_path.write_text(json.dumps(ratings))
    with pytest.raises(ValueError,match='duplicate'):summarize_ratings(output/'blinded-cases.json',rating_path)


def test_repeated_models_receive_identical_frozen_evidence_and_failures_are_retained(tmp_path,monkeypatch):
    from allelio import evaluation
    from allelio.ai.attribution import Explanation
    from allelio.ai.prompts import build_variant_prompt
    prompts=[]
    class Model:
        provider='synthetic-local';status='serving';model_digest=None;max_tokens=50;request_timeout=1
        def __init__(self,model):self.model=model
        async def check_connection(self):return True
        async def explain(self,finding):
            prompts.append((self.model,build_variant_prompt(finding)))
            return Explanation('Synthetic text',self.model if self.model!='failed' else None)
    monkeypatch.setattr(evaluation,'AIEngine',Model)
    # Preserve the actual deterministic baseline helper on the controlled adapter.
    from allelio.ai.engine import AIEngine
    Model._fallback_explanation=AIEngine._fallback_explanation
    output=tmp_path/'eval';result=generate_evaluation(ROOT/'examples/evaluation/bundle.json',output,['model-a','failed'],2)
    assert result=={'generated_cases':6,'failed_outputs':4,'outputs':10}
    assert [p for m,p in prompts if m=='model-a']==[p for m,p in prompts if m=='failed']
    assert prompts[0][1]==prompts[1][1]
    private=json.loads((output/'private-run.json').read_text())
    assert private['arms'][1]['repetitions']==2
    assert private['arms'][2]['provenance']['fallback_status']=='all'


def test_cli_generates_and_summarizes_template_only(tmp_path):
    output=tmp_path/'eval';runner=CliRunner()
    result=runner.invoke(allelio,['evaluate-explanations',str(ROOT/'examples/evaluation/bundle.json'),'--output',str(output)])
    assert result.exit_code==0,result.output
    result=runner.invoke(allelio,['summarize-ratings',str(output/'blinded-cases.json'),str(output/'ratings-template.json'),'--output',str(output/'summary.json')])
    assert result.exit_code==0,result.output
    report=json.loads((output/'summary.json').read_text())
    assert all(r['missing']==report['expected_rows'] for r in report['dimensions'].values())
