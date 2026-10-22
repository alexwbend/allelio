#!/usr/bin/env python3
"""Run the frozen two-case internal explanation pilot, retaining local receipts."""
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from allelio import evaluation
from allelio.ai.engine import AIEngine, _split_answer_and_reasoning
from allelio.ai.prompts import SYSTEM_PROMPT, build_variant_prompt
from allelio.ai.safety import check_safety, find_unsafe_language, get_variant_warnings, wrap_with_disclaimer
from allelio.evidence import write_evidence_export as write
from allelio.runs import checksum, code_identity, runtime_identity

PROTOCOL = ROOT / 'data/evaluation/explanation-pilot-v1.protocol.json'
INPUTS = ('bundle.json', 'evidence.json', 'run.json')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def frozen(protocol):
    require(protocol['schema'] == 'allelio-explanation-pilot/1'
            and protocol['data_kind'] == 'synthetic'
            and protocol['independent_validation'] is False, 'Internal synthetic protocol required.')
    require(protocol['software'] == code_identity(), 'Software differs from frozen protocol.')
    require(protocol['runner_sha256'] == checksum(__file__), 'Runner differs from frozen protocol.')
    fixture = ROOT / 'examples/evaluation'
    require(set(protocol['inputs']) == set(INPUTS), 'Unexpected input inventory.')
    require(all(checksum(fixture / name) == protocol['inputs'][name] for name in INPUTS),
            'Input differs from frozen protocol.')
    bundle, cases = evaluation.load_cases(fixture / 'bundle.json')
    require(bundle['data_kind'] == 'synthetic' and len(cases) == 2, 'Two invented cases required.')
    require(protocol['system_prompt_sha256'] == text_hash(SYSTEM_PROMPT)
            and protocol['case_prompt_sha256'] == {
                c['id']: text_hash(build_variant_prompt(c['finding'])) for c in cases},
            'Prompts differ from frozen protocol.')
    return cases


def outputs(directory):
    return json.loads((directory / 'private-run.json').read_text())['outputs']


def template_checks(rows, cases):
    require(len(rows) == len(cases) and len({r['case_id'] for r in rows}) == len(cases),
            'Template case accounting failed.')
    result = []
    for case in cases:
        row = next(r for r in rows if r['case_id'] == case['id'])
        expected = AIEngine._fallback_explanation(None, case['finding'], reason='Reference annotation')
        finding = case['finding']
        required = [finding.rsid, finding.genotype, 'Inheritance (ClinGen): not curated',
                    'healthcare provider']
        required += [e.conditions + ': ' + e.clinical_significance for e in finding.clinvar_entries]
        result.append({'case_id': case['id'], 'text_sha256': text_hash(row['text']),
                       'generated': row['status'] == 'generated', 'template_exact': row['text'] == expected,
                       'selected_fields_present': all(s in row['text'] for s in required)})
    return result


@contextmanager
def settings(protocol):
    # The experiment fixes only options actually supported by the production adapter.
    # Server sampling defaults are retained as unknown effective settings.
    changes = {'ALLELIO_MAX_TOKENS': str(protocol['generation']['max_tokens']),
               'ALLELIO_REQUEST_TIMEOUT': str(protocol['generation']['timeout_seconds'])}
    with patch.dict(os.environ, changes):
        previous = {k: os.environ.pop(k, None) for k in ('ALLELIO_OPENAI_BASE', 'ALLELIO_MODEL')}
        try:
            yield
        finally:
            os.environ.update({k: v for k, v in previous.items() if v is not None})


def model_metadata(protocol):
    import httpx
    # Fixed local address; no redirects, proxies or credentials.
    with httpx.Client(base_url='http://127.0.0.1:11434', trust_env=False,
                      follow_redirects=False, timeout=15) as client:
        version = client.get('/api/version'); version.raise_for_status()
        require(version.json()['version'] == protocol['ollama_version'], 'Ollama version changed.')
        tags = client.get('/api/tags'); tags.raise_for_status()
        listed = {m['name']: m for m in tags.json()['models']}
        result = {}
        for model in protocol['models']:
            require(listed.get(model['name'], {}).get('digest') == model['digest'], 'Model digest changed.')
            show = client.post('/api/show', json={'model': model['name']}); show.raise_for_status()
            # Deliberately exclude modelfile paths, installation dates and host metadata.
            info = show.json()
            result[model['name']] = {'digest': model['digest'],
                **{k: info.get(k) for k in ('details', 'parameters', 'template', 'license', 'capabilities')}}
    return result


def recorder(cases, protocol, directory):
    receipts = []
    case_ids = {c['finding'].rsid: c['id'] for c in cases}
    repetitions = Counter()
    class RecordedEngine(AIEngine):
        async def check_connection(self):
            connected = await super().check_connection()
            expected = next(m['digest'] for m in protocol['models'] if m['name'] == self.model)
            require(self.status == 'serving' and self.model_digest == expected,
                    'Selected local model is not serving the frozen digest.')
            return connected

        async def explain(self, finding):
            started = time.monotonic()
            original = self.client
            received = {}
            class ClientReceipt:
                async def chat(inner, **kwargs):
                    require([text_hash(m['content']) for m in kwargs['messages']] == [
                        protocol['system_prompt_sha256'], protocol['case_prompt_sha256'][case_ids[finding.rsid]]],
                        'Actual request differs from frozen prompts.')
                    received.update({'request_messages': kwargs['messages'],
                                     'request_options': kwargs.get('options')})
                    response = await original.chat(**kwargs)
                    answer, reasoning = _split_answer_and_reasoning(response['message'])
                    def field(key):
                        return response.get(key) if isinstance(response, dict) else getattr(response, key, None)
                    received.update({'answer': answer, 'reasoning_chars_removed': len(reasoning or ''),
                        'response': {k: field(k) for k in ('model', 'done', 'done_reason',
                            'total_duration', 'load_duration', 'prompt_eval_count', 'prompt_eval_duration',
                            'eval_count', 'eval_duration') if field(k) is not None}})
                    return response
            self.client = ClientReceipt()
            try:
                explanation = await super().explain(finding)
            finally:
                self.client = original
            case_id = case_ids[finding.rsid]
            repetitions[self.model, case_id] += 1
            answer = received.get('answer')
            expected = None
            if answer is not None and answer.strip():
                cleaned, _ = check_safety(answer)
                expected = wrap_with_disclaimer(cleaned, get_variant_warnings(finding))
            receipt = {'case_id': case_id, 'model': self.model,
                'repeat': repetitions[self.model, case_id], 'elapsed_seconds': time.monotonic() - started,
                'status': 'generated' if explanation.model else 'fallback', 'error': explanation.error,
                'final_text': explanation.text, 'final_text_sha256': text_hash(explanation.text),
                'lexical_categories': sorted({m.category for m in find_unsafe_language(answer or '')}),
                'wrapper_matches': explanation.text == expected if explanation.model else None, **received}
            # Reasoning content is never retained; only its removed character count.
            receipts.append(receipt)
            write(receipt, directory / ('call-%02d.json' % len(receipts)))
            print(f"Retained call {len(receipts)}: {self.model}, {case_id}, {receipt['status']}", flush=True)
            return explanation
    return RecordedEngine, receipts


def run(output, mode, baseline=None, protocol_path=PROTOCOL):
    protocol_path = Path(protocol_path)
    protocol_bytes = protocol_path.read_bytes()
    protocol = json.loads(protocol_bytes)
    cases = frozen(protocol)
    require(mode in ('template', 'models'), 'Unknown mode.')
    output = Path(output).resolve()
    require(not any((p / '.git').exists() for p in (output, *output.parents)),
            'Keep original experiment records outside Git checkouts.')
    require(not output.exists(), 'Use a new output directory; preserve previous attempts.')
    output.mkdir(parents=True, mode=0o700)
    (output / 'INCOMPLETE').write_text('Preserve this attempt even if execution fails.\n')
    (output / 'protocol.json').write_bytes(protocol_bytes)
    fixture = output / 'inputs'; fixture.mkdir()
    for name in INPUTS:
        shutil.copyfile(ROOT / 'examples/evaluation' / name, fixture / name)
    report = {'schema': 'allelio-explanation-pilot-result/1', 'mode': mode,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'protocol_sha256': checksum(protocol_path), 'software': code_identity(),
        'runtime': runtime_identity(), 'independent_validation': False,
        'distinct_cases': len(cases), 'human_ratings': 0, 'human_inspections': 0}
    try:
        if mode == 'template':
            def deny(*args, **kwargs):
                raise AssertionError('Template baseline attempted network access.')
            with patch.object(socket.socket, 'connect', deny), patch.object(socket, 'getaddrinfo', deny):
                evaluation.generate_evaluation(fixture / 'bundle.json', output / 'baseline')
                evaluation.generate_evaluation(fixture / 'bundle.json', output / 'repeat-check')
            rows = outputs(output / 'baseline')
            repeated = outputs(output / 'repeat-check')
            require(rows == repeated, 'Deterministic template changed between runs.')
            checks = template_checks(rows, cases)
            require(all(all(r[k] for k in ('generated', 'template_exact', 'selected_fields_present'))
                        for r in checks), 'Template integrity check failed.')
            report.update({'template_checks': checks, 'repeat_identical': True,
                           'model_calls': 0, 'network_guard': 'socket connect and DNS denied in process'})
        else:
            require(baseline is not None, 'Run and retain the template baseline first.')
            baseline = Path(baseline)
            prior = json.loads((baseline / 'summary.json').read_text())
            require(prior['mode'] == 'template' and prior['protocol_sha256'] == checksum(protocol_path)
                    and prior.get('repeat_identical') is True, 'Baseline protocol differs or is incomplete.')
            require(not (baseline / 'INCOMPLETE').exists(), 'Baseline is incomplete.')
            require(all(checksum(baseline / name) == digest for name, digest in prior['artifacts'].items()),
                    'Retained baseline artifacts changed.')
            before = model_metadata(protocol); write(before, output / 'model-metadata.json')
            calls = output / 'calls'; calls.mkdir()
            engine, receipts = recorder(cases, protocol, calls)
            with settings(protocol), patch.object(evaluation, 'AIEngine', engine):
                evaluation.generate_evaluation(fixture / 'bundle.json', output / 'evaluation',
                    [m['name'] for m in protocol['models']], protocol['generation']['repetitions'])
            rows = outputs(output / 'evaluation')
            template = [r for r in rows if r['arm'] == 'template']
            require(template == outputs(baseline / 'baseline'), 'Paired template differs from baseline.')
            require(model_metadata(protocol) == before, 'Model resources changed during execution.')
            require(len(receipts) == len(cases) * len(protocol['models']) * protocol['generation']['repetitions'],
                    'Missing call receipts.')
            require(all(r['wrapper_matches'] is True for r in receipts if r['status'] == 'generated'),
                    'Production safety/disclaimer output differed from recorded answer.')
            arms = []
            for index, model in enumerate(protocol['models'], 1):
                group = [r for r in receipts if r['model'] == model['name']]
                arm_rows = [r for r in rows if r['arm'] == f'model-{index}']
                require([(r['case_id'], r['repeat'], r['status'], r['final_text']) for r in group]
                        == [(r['case_id'], r['repeat'], r['status'], r['text']) for r in arm_rows],
                        'Call receipts and evaluation outputs differ.')
                arms.append({'model': model['name'], 'digest': model['digest'],
                    'opportunities': len(group), 'statuses': dict(Counter(r['status'] for r in group)),
                    'lexically_flagged_outputs': sum(bool(r['lexical_categories']) for r in group),
                    'reasoning_removed_outputs': sum(r.get('reasoning_chars_removed', 0) > 0 for r in group),
                    'length_stopped_outputs': sum(r.get('response', {}).get('done_reason') == 'length' for r in group),
                    'wrapper_verified_outputs': sum(r['wrapper_matches'] is True for r in group),
                    'outputs': [{'case_id': r['case_id'], 'repeat': r['repeat'], 'status': r['status'],
                                 'text_sha256': r['final_text_sha256']} for r in group]})
            report.update({'baseline_summary_sha256': checksum(baseline / 'summary.json'),
                           'model_calls': len(receipts), 'arms': arms,
                           'template_checks': template_checks(template, cases)})
        require(protocol_path.read_bytes() == protocol_bytes, 'Protocol changed during execution.')
        frozen(protocol)
        require(all(checksum(fixture / name) == protocol['inputs'][name] for name in INPUTS),
                'Retained input copy changed during execution.')
        report['status'] = 'complete'
        report['artifacts'] = {p.relative_to(output).as_posix(): checksum(p)
                               for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'INCOMPLETE'}
        write(report, output / 'summary.json')
        (output / 'INCOMPLETE').unlink()
        return report
    except BaseException as exc:
        # Local diagnostics may contain server-controlled details. Never publish wholesale.
        write({'type': type(exc).__name__, 'error': str(exc)}, output / 'failure.json')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('template', 'models'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    result = run(args.output, args.mode, args.baseline)
    print(json.dumps({k: result[k] for k in ('status', 'mode', 'distinct_cases', 'model_calls')}))
