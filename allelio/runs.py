"""Local, content-addressed annotation runs. Replay never downloads or calls AI."""
import asyncio
import hashlib
import json
import platform
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from allelio import __version__
from allelio.analysis.lookup import analyze_variants_with_stats, PGX_DEFAULT_MIN_LEVEL, PGX_LEVEL_RANKS
from allelio.database.store import AllelioDB
from allelio.evidence import build_evidence_export
from allelio.parsers.base import parse_genotype_file_with_stats

SCHEMA = 'allelio-run/1'
OPTIONS = {'include_benign': False, 'include_reference': False,
           'frequency_adjustment': True, 'traits_only': False, 'detailed_trace': False, 'pgx_min_level': PGX_DEFAULT_MIN_LEVEL}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode()


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def code_identity():
    """Works in wheels and source installs, without git, paths or environment dumps."""
    root = Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.suffix in ('.py', '.json', '.html'):
            digest.update(canonical([path.relative_to(root).as_posix(), checksum(path)]))
    return {'package': 'allelio', 'version': __version__, 'content_sha256': digest.hexdigest()}


def runtime_identity():
    versions = {}
    for name in ('click', 'jsonschema', 'httpx', 'ollama'):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return {'python': platform.python_version(), 'implementation': platform.python_implementation(),
            'sqlite': sqlite3.sqlite_version, 'packages': versions}


@contextmanager
def references(path):
    """Read a fixed SQLite snapshot; do not create, migrate or replace references."""
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('Reference database is missing; provide the recorded database explicitly.')
    db = object.__new__(AllelioDB)
    db.db_path = path
    db.conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    db.conn.row_factory = sqlite3.Row
    db.cursor = db.conn.cursor()
    try:
        db.conn.execute('PRAGMA query_only=ON')
        db.conn.execute('BEGIN')
        if not db.is_initialized():
            raise ValueError('Reference database is not initialized; no downloads were attempted.')
        yield db
    finally:
        db.close()


def reference_identity(db):
    """Hash logical rows, including WAL contents, independent of SQLite file layout."""
    digest = hashlib.sha256()
    tables = db.conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    for name, definition in tables:
        quoted = '"' + name.replace('"', '""') + '"'
        columns = db.conn.execute('PRAGMA table_info(' + quoted + ')').fetchall()
        order = ','.join(str(i + 1) for i in range(len(columns)))
        digest.update(canonical([name, definition]))
        for row in db.conn.execute('SELECT * FROM ' + quoted + ' ORDER BY ' + order):
            # Typed bytes cannot collide with strings; non-finite floats are
            # represented by their exact hexadecimal form rather than invalid JSON.
            values = [[type(v).__name__, v.hex() if isinstance(v, (bytes, float)) else v] for v in row]
            digest.update(canonical(values))
    provenance = db.get_provenance()
    return {'logical_sha256': digest.hexdigest(), 'sources': {
        name: {key: record.get(key) for key in ('release', 'sha256')}
        for name, record in provenance.items()}}


def annotation(file, db, options):
    variants, _ = parse_genotype_file_with_stats(str(file))
    results, stats = analyze_variants_with_stats(variants, db,
        include_benign=options['include_benign'], include_reference=options['include_reference'],
        frequency_adjustment=options['frequency_adjustment'], pgx_min_level=options['pgx_min_level'])
    if options['traits_only']:
        results = [r for r in results if r.category == 'Traits']
    # URL/path metadata is unnecessary to reproduce annotation and may contain
    # credentials. Only release names and source hashes belong in this artifact.
    provenance = {name: {key: row.get(key) for key in ('release', 'sha256')}
                  for name, row in db.get_provenance().items()}
    evidence = build_evidence_export(results, variants, provenance, options, stats,
                                     detailed_trace=options['detailed_trace'])
    return evidence, results


def annotation_checksum(evidence):
    return hashlib.sha256(canonical({k: v for k, v in evidence.items() if k != 'generated_at'})).hexdigest()


def explanation_provenance(engine, requested, top, explanations, configured_model=None):
    template = Path(__file__).parent / 'ai' / 'prompts.py'
    written = sum(bool(e.model) for e in explanations.values())
    return {'requested': requested, 'prompt_template_sha256': checksum(template),
            'configured_model': configured_model, 'backend': getattr(engine, 'provider', None), 'model': getattr(engine, 'model', None),
            'model_digest': getattr(engine, 'model_digest', None),
            'connection_status': getattr(engine, 'status', None),
            'generation': {'top': top, 'max_tokens': getattr(engine, 'max_tokens', None),
                           'timeout_seconds': getattr(engine, 'request_timeout', None),
                           'temperature': None, 'seed': None, 'repetitions': 1},
            'outputs': len(explanations), 'model_outputs': written,
            'fallback_outputs': len(explanations) - written,
            'fallback_status': ('not_requested' if not requested else
                                'not_generated' if not explanations else
                                'none' if written == len(explanations) else
                                'all' if not written else 'partial'),
            'replay': 'annotation_only; model outputs are not reproduced or embedded'}


def record_run(file, database, options=None, explain=False, model=None, top=20):
    options = dict(OPTIONS, **(options or {}))
    if set(options) != set(OPTIONS) or any(type(v) is not bool for k, v in options.items() if k != "pgx_min_level") or options["pgx_min_level"] not in PGX_LEVEL_RANKS:
        raise ValueError('Unsupported annotation options.')
    if type(top) is not int or top < 0:
        raise ValueError('Explanation limit must be nonnegative.')
    software = code_identity()
    original = checksum(file)
    with references(database) as db:
        identity = reference_identity(db)
        evidence, results = annotation(file, db, options)
    if checksum(file) != original:
        raise ValueError('Input changed during annotation; run was not recorded.')
    engine, explanations, configured_model = None, {}, None
    if explain:
        from allelio.ai.engine import AIEngine, REFUSED
        engine = AIEngine(model=model)
        configured_model = engine.model
        async def generate():
            await engine.check_connection()
            if engine.status == REFUSED:
                raise ValueError('Configured model is refused; no explanation was generated.')
            for result in sorted(results, key=lambda r: r.significance_rank)[:top]:
                explanations[result.rsid] = await engine.explain(result)
        asyncio.run(generate())
    if software != code_identity():
        raise ValueError('Allelio package changed during the run; run was not recorded.')
    manifest = {'schema': SCHEMA, 'created_at': datetime.now(timezone.utc).isoformat(),
                'software': software, 'runtime': runtime_identity(),
                'input': {'sha256': original}, 'references': identity, 'options': options,
                'annotation_sha256': annotation_checksum(evidence),
                'explanations': explanation_provenance(engine, explain, top, explanations, configured_model)}
    return manifest, evidence, explanations


def replay_run(manifest, file, database, verify_only=False):
    """Verify immutable prerequisites before parsing; AI is never contacted."""
    validate_manifest(manifest)
    if manifest['software'] != code_identity():
        raise ValueError('Allelio package contents/version changed; use the recorded installation.')
    if manifest['input']['sha256'] != checksum(file):
        raise ValueError('Input checksum differs from the recorded run.')
    with references(database) as db:
        if manifest['references'] != reference_identity(db):
            raise ValueError('Reference contents/provenance changed; restore the recorded database. No downloads attempted.')
        evidence = None
        if not verify_only:
            evidence, _ = annotation(file, db, manifest['options'])
            if checksum(file) != manifest['input']['sha256']:
                raise ValueError('Input changed during replay.')
            if annotation_checksum(evidence) != manifest['annotation_sha256']:
                raise ValueError('Annotation differs from recorded output (including runtime-dependent behavior).')
    current_runtime = runtime_identity()
    return {'verified': True, 'annotation_replayed': not verify_only,
            'runtime_differences': {key: {'recorded': value, 'current': current_runtime[key]}
                                    for key, value in manifest['runtime'].items()
                                    if current_runtime.get(key) != value},
            'explanations_replayed': False}, evidence


def validate_manifest(manifest):
    """Reject malformed/unversioned documents before opening user inputs."""
    from jsonschema import Draft202012Validator
    schema = json.loads((Path(__file__).parent / 'schemas' / 'run-1.json').read_text())
    errors = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda e: str(e.path))
    if errors:
        raise ValueError('Invalid run manifest: ' + errors[0].message)
