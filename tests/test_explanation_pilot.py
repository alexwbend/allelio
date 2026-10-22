"""Offline checks of pilot integrity and per-call failure accounting."""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('explanation_pilot', ROOT / 'scripts/run_explanation_pilot.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


@pytest.fixture
def protocol(tmp_path):
    _, cases = pilot.evaluation.load_cases(ROOT / 'examples/evaluation/bundle.json')
    value = {'schema': 'allelio-explanation-pilot/1', 'data_kind': 'synthetic',
        'independent_validation': False, 'software': pilot.code_identity(),
        'runner_sha256': pilot.checksum(pilot.__file__),
        'inputs': {name: pilot.checksum(ROOT / 'examples/evaluation' / name) for name in pilot.INPUTS},
        'system_prompt_sha256': pilot.text_hash(pilot.SYSTEM_PROMPT),
        'case_prompt_sha256': {c['id']: pilot.text_hash(pilot.build_variant_prompt(c['finding'])) for c in cases},
        'generation': {'max_tokens': 4096, 'timeout_seconds': 900, 'repetitions': 3},
        'models': [{'name': 'synthetic-local', 'digest': 'a' * 64}]}
    path = tmp_path / 'protocol.json'; path.write_text(json.dumps(value))
    return path, value, cases


def test_template_baseline_guards_network_and_preserves_first_attempt(protocol, tmp_path):
    path, _, _ = protocol
    target = tmp_path / 'baseline'
    report = pilot.run(target, 'template', protocol_path=path)
    assert report['repeat_identical'] and report['model_calls'] == 0
    assert report['distinct_cases'] == 2 and report['human_ratings'] == 0
    assert all(c['selected_fields_present'] for c in report['template_checks'])
    assert not (target / 'INCOMPLETE').exists()
    with pytest.raises(ValueError, match='new output'):
        pilot.run(target, 'template', protocol_path=path)


def test_changed_inputs_or_prompts_are_rejected(protocol):
    _, value, _ = protocol
    for field in ('inputs', 'case_prompt_sha256'):
        changed = copy.deepcopy(value)
        changed[field][next(iter(changed[field]))] = '0' * 64
        with pytest.raises(ValueError, match='differs|differ'):
            pilot.frozen(changed)


def test_receipts_separate_reasoning_safety_flags_and_timeout_fallback(protocol, tmp_path):
    _, value, cases = protocol
    observed, receipts = pilot.recorder(cases, value, tmp_path)
    class Client:
        fail = False
        async def chat(self, **kwargs):
            if self.fail:
                raise asyncio.TimeoutError()
            # Final answer is intentionally flagged; a reasoning fragment is discarded.
            return {'message': {'content': '<think>PRIVATE REASONING</think>You have cancer.'},
                    'done': True, 'done_reason': 'length', 'eval_count': 4096}
    with pilot.settings(value):
        engine = observed(model='synthetic-local')
    engine.available = engine.listed = True
    engine.served_models = ['synthetic-local']
    engine.client = Client()
    generated = asyncio.run(engine.explain(cases[0]['finding']))
    assert generated.model is not None
    assert receipts[0]['wrapper_matches'] is True and receipts[0]['lexical_categories']
    assert receipts[0]['reasoning_chars_removed'] > 0
    assert receipts[0]['response']['done_reason'] == 'length'
    assert 'PRIVATE REASONING' not in (tmp_path / 'call-01.json').read_text()
    engine.client.fail = True
    fallback = asyncio.run(engine.explain(cases[0]['finding']))
    assert fallback.model is None and fallback.error == 'Request timed out'
    assert receipts[1]['status'] == 'fallback' and receipts[1]['error'] == fallback.error
    assert receipts[1]['wrapper_matches'] is None and 'answer' not in receipts[1]


def test_model_run_requires_complete_unchanged_baseline_before_contact(protocol, tmp_path, monkeypatch):
    path, _, _ = protocol
    baseline = tmp_path / 'baseline'
    pilot.run(baseline, 'template', protocol_path=path)
    (baseline / 'baseline/private-run.json').write_text('{}')
    def forbidden(*args):
        raise AssertionError('Should reject changed baseline before contacting models')
    monkeypatch.setattr(pilot, 'model_metadata', forbidden)
    with pytest.raises(ValueError, match='artifacts changed'):
        pilot.run(tmp_path / 'models', 'models', baseline, path)
    assert (tmp_path / 'models/INCOMPLETE').exists()
    assert (tmp_path / 'models/failure.json').is_file()


def test_model_summary_retains_paired_denominators_and_fallbacks(protocol, tmp_path, monkeypatch):
    path, _, _ = protocol
    baseline = tmp_path / 'baseline'
    pilot.run(baseline, 'template', protocol_path=path)
    monkeypatch.setattr(pilot, 'model_metadata', lambda _: {'synthetic-local': {'digest': 'a' * 64}})
    async def connected(self):
        self.available = self.listed = True
        self.served_models = [self.model]
        self.model_digest = 'a' * 64
        return True
    async def chat(self, **kwargs):
        if 'rs99002' in kwargs['messages'][1]['content']:
            raise asyncio.TimeoutError()
        return {'message': {'content': 'Synthetic answer.'}, 'done_reason': 'stop'}
    monkeypatch.setattr(pilot.AIEngine, 'check_connection', connected)
    from ollama import AsyncClient
    monkeypatch.setattr(AsyncClient, 'chat', chat)
    report = pilot.run(tmp_path / 'models', 'models', baseline, path)
    assert report['model_calls'] == 6 and report['distinct_cases'] == 2
    arm = report['arms'][0]
    assert arm['statuses'] == {'generated': 3, 'fallback': 3}
    assert arm['wrapper_verified_outputs'] == 3 and len(arm['outputs']) == 6
