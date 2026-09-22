"""Conservative, development-only import of frozen offline VEP JSON output.

This adapter measures VCF parsing only. Consequences and colocated rsIDs are
never promoted to Allelio source-selection or allele-matching observations.
"""
import hashlib
import json
import re
from pathlib import Path

from allelio.benchmark import STAGES, local_file
from allelio.evidence import write_evidence_export
from allelio.runs import checksum


SCHEMA = 'allelio-vep-import/1'


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + ' must be a nonempty string.')
    return value


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('Expected a lowercase SHA-256 fingerprint.')
    return value


def _resource(root, spec, retain=True):
    if not isinstance(spec, dict):
        raise ValueError('Resources must be objects with paths and hashes.')
    path = local_file(root, spec['path'])
    expected = _sha(spec['sha256'])
    if not retain:
        # Cache archives can be many gigabytes; never materialize them in RAM.
        if checksum(path) != expected:
            raise ValueError('Resource checksum differs: ' + spec['path'])
        return None
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Resource checksum differs: ' + spec['path'])
    return data


def _parsing(input_bytes, raw_bytes, assembly):
    """Compare exact original VCF rows; restrict shared scope to called SNPs."""
    lines = input_bytes.decode('utf-8').splitlines()
    if not lines or not lines[0].startswith('##fileformat=VCFv4.'):
        return 'unsupported', 'consumer_array_or_non_vcf_input'
    headers = [line for line in lines if line.startswith('#CHROM\t')]
    expected_header = ['#CHROM', 'POS', 'ID', 'REF', 'ALT', 'QUAL', 'FILTER', 'INFO', 'FORMAT']
    if (len(headers) != 1 or len(headers[0].split('\t')) != 10
            or headers[0].split('\t')[:9] != expected_header):
        return 'unsupported', 'requires_one_sample_vcf'
    if [line for line in lines if line.startswith('##reference=')] != ['##reference=' + assembly]:
        return 'unsupported', 'requires_explicit_matching_reference'
    records = [line.split('\t') for line in lines if line and not line.startswith('#')]
    if not records:
        return 'unsupported', 'empty_vcf'
    identities, rsids = set(), set()
    for row in records:
        if (len(row) != 10 or not re.fullmatch(r'rs[0-9]+', row[2])
                or not row[1].isdigit() or int(row[1]) < 1
                or row[3] not in 'ACGT' or len(row[3]) != 1
                or row[4] not in 'ACGT' or len(row[4]) != 1 or row[3] == row[4]
                or row[6] not in ('.', 'PASS')):
            return 'unsupported', 'requires_unfiltered_biallelic_snp_with_rsid'
        fields = row[8].split(':')
        values = row[9].split(':')
        if len(fields) != len(values) or len(set(fields)) != len(fields):
            return 'unsupported', 'ambiguous_sample_fields'
        sample = dict(zip(fields, values))
        if not re.fullmatch(r'[01](?:[/|][01])?', sample.get('GT', '')) or sample.get('FT', '.') not in ('.', 'PASS'):
            return 'unsupported', 'missing_unsupported_or_filtered_genotype'
        identity = tuple(row[:2])
        if identity in identities or row[2] in rsids:
            return 'unsupported', 'duplicate_input'
        identities.add(identity)
        rsids.add(row[2])
    originals = {tuple(row) for row in records}
    emitted = set()
    for line in raw_bytes.decode('utf-8').splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict) or not isinstance(obj.get('input'), str):
            raise ValueError('VEP JSON rows require the original input field.')
        original = tuple(obj['input'].split())
        if original not in originals:
            raise ValueError('VEP output contains an input row absent from the frozen VCF.')
        if original in emitted:
            raise ValueError('Duplicate VEP output row.')
        emitted.add(original)
    # The benchmark parsing outcome means at least one retained input. Retain
    # raw output separately; it is not an assertion that every row parsed.
    return ('parsed' if emitted else 'excluded'), {
        'input_records': len(records), 'emitted_records': len(emitted),
        'omitted_records': len(originals - emitted),
    }


def import_vep(manifest_path, output):
    """Verify and preserve a development run without executing external code."""
    manifest_path = Path(manifest_path)
    root = manifest_path.parent
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict) or manifest.get('schema') != SCHEMA or manifest.get('split') != 'development':
        raise ValueError('Only development VEP imports are supported; held-out runs remain frozen.')
    _text(manifest.get('license'), 'Reuse license')
    version = _text(manifest.get('vep_version'), 'VEP version')
    _text(manifest.get('hardware'), 'Hardware')
    assembly = manifest.get('assembly')
    if assembly not in ('GRCh37', 'GRCh38'):
        raise ValueError('Assembly must be GRCh37 or GRCh38.')
    resources = manifest.get('resources')
    if not isinstance(resources, list) or not resources or any(not isinstance(r, dict) for r in resources):
        raise ValueError('Pinned VEP resources are required.')
    if not {'software', 'cache'} <= {r.get('kind') for r in resources}:
        raise ValueError('Pin both VEP software and cache resources.')
    verified = []
    for resource in resources:
        _text(resource.get('version'), 'Resource version')
        _resource(root, resource, retain=False)
        verified.append(resource['sha256'])
    # An empty plugin list is explicit. Plugins must also have pinned resources.
    plugins = manifest.get('plugins')
    plugin_hashes = [r['sha256'] for r in resources if r.get('kind') == 'plugin']
    if (not isinstance(plugins, list) or any(not isinstance(p, str) for p in plugins)
            or len(set(plugins)) != len(plugins) or sorted(plugins) != sorted(plugin_hashes)):
        raise ValueError('Plugins must list exactly the pinned plugin resource hashes, or be explicitly empty.')
    cases = manifest.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('At least one development case is required.')
    rows, artifacts, seen = [], {}, set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError('Cases must be objects.')
        case_id = case.get('id')
        if not isinstance(case_id, str) or not re.fullmatch(r'[a-z0-9_-]+', case_id) or case_id in seen:
            raise ValueError('Cases require unique safe IDs.')
        seen.add(case_id)
        approval = case['alignment']
        if not isinstance(approval, dict):
            raise ValueError('Alignment approval must be an object.')
        _text(approval.get('reviewer'), 'Alignment reviewer')
        _text(approval.get('date'), 'Alignment date')
        _text(approval.get('rationale'), 'Alignment rationale')
        if approval.get('approved') is not True or sorted(approval.get('resource_sha256', [])) != sorted(verified):
            raise ValueError('Approval must bind the exact VEP resource fingerprints.')
        reference_sha = _sha(approval.get('allelio_references_sha256'))
        if _sha(approval.get('input_sha256')) != case['input']['sha256']:
            raise ValueError('Alignment approval must bind the exact input fingerprint.')
        command = case.get('command')
        if not isinstance(command, list) or not command or any(not isinstance(arg, str) for arg in command):
            raise ValueError('Record the command as an argument list.')
        if not {'--offline', '--cache', '--json'} <= set(command) or '--database' in command:
            raise ValueError('Recorded command must use offline cache JSON mode.')
        if (command.count('--assembly') != 1 or command.index('--assembly') + 1 >= len(command)
                or command[command.index('--assembly') + 1] != assembly):
            raise ValueError('Recorded command must explicitly select the declared assembly.')
        if case.get('exit_code') != 0 or type(case.get('exit_code')) is not int:
            raise ValueError('Failed VEP runs cannot be scored as exclusions.')
        input_bytes = _resource(root, case['input'])
        raw_bytes = _resource(root, case['raw_output'])
        log_bytes = _resource(root, case['log'])
        parsing, detail = _parsing(input_bytes, raw_bytes, assembly)
        reason = detail if parsing == 'unsupported' else None
        counts = detail if parsing != 'unsupported' else None
        outcomes = dict.fromkeys(STAGES, 'unsupported')
        outcomes['parsing'] = parsing
        rows.append({'id': case_id, 'input_sha256': case['input']['sha256'],
                     'references_sha256': reference_sha, 'outcomes': outcomes,
                     'scope_reason': reason, 'parsing_counts': counts, 'raw_output': case_id + '/vep.jsonl',
                     'raw_output_sha256': case['raw_output']['sha256'],
                     'alignment': approval,
                     'unsupported_stages': {stage: 'No validated equivalent stage mapping.'
                                            for stage in STAGES if outcomes[stage] == 'unsupported'}})
        artifacts[case_id] = (input_bytes, raw_bytes, log_bytes)
    report = {'schema': 'allelio-benchmark/1', 'tool': {'name': 'Ensembl VEP', 'version': version},
              'adapter': 'allelio-vep-import/1', 'split': 'development', 'cases': rows,
              'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
              'provenance': manifest,
              'limitations': ['Only called, unfiltered, single-sample biallelic SNP VCF parsing is compared.',
                              'Reference alignment is a recorded reviewer assertion, not inferred or independently verified.',
                              'Command metadata does not prove network isolation or execution authenticity.',
                              'Source agreement is not clinical ground truth.']}
    output = Path(output)
    if output.exists():
        raise ValueError('Use a new output directory to preserve prior runs.')
    output.mkdir(parents=True)
    (output / 'import-manifest.json').write_bytes(manifest_bytes)
    for case_id, blobs in artifacts.items():
        directory = output / case_id
        directory.mkdir()
        for filename, blob in zip(('input.txt', 'vep.jsonl', 'vep.log'), blobs):
            (directory / filename).write_bytes(blob)
    write_evidence_export(report, output / 'benchmark.json')
    return report
