"""The evidence JSON has a shipped, checkable contract.

Structural validation is JSON Schema 2020-12 (allelio/schemas); reference and
count conservation checks live in allelio.schema. Fixtures under
tests/fixtures/evidence_schema/ are small synthetic documents.
"""

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from allelio import evidence, schema
from allelio.analysis.example_check import EXAMPLE_FILE, build_fixture_db, run_example
from allelio.database import provenance_of
from allelio.evidence import build_evidence_export
from allelio.schema import load_schema, semantic_errors, validate_evidence, validate_evidence_file

FIXTURES = Path(__file__).parent / "fixtures" / "evidence_schema"
ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _roundtrip(document):
    return json.loads(json.dumps(document, allow_nan=False))


@pytest.fixture(scope="module")
def example_db(tmp_path_factory):
    return build_fixture_db(str(tmp_path_factory.mktemp("schema") / "example.db"))


class TestSchemaDocument:
    def test_ships_the_pinned_dialect_and_version(self):
        doc = load_schema()
        assert doc["$schema"] == schema.SCHEMA_DIALECT
        assert doc["$id"].endswith(f"evidence-{schema.DEFAULT_SCHEMA_VERSION}.json")
        assert schema.DEFAULT_SCHEMA_VERSION == evidence.SCHEMA_VERSION
        assert "not VRS IDs" in doc["description"] and "additional" in doc["description"]
        jsonschema = pytest.importorskip("jsonschema")
        jsonschema.Draft202012Validator.check_schema(doc)

    def test_describes_every_section(self):
        doc = load_schema()
        assert set(doc["required"]) == {"schema_version", "software", "generated_at", "configuration", "provenance",
                                        "inputs", "findings", "gene_groups", "coverage", "limitations"}
        assert set(doc["$defs"]) >= {"input", "finding", "clinvar_entry", "gwas_entry", "gnomad_entry", "clingen_entry",
                                     "pgx_entry", "inheritance_resolution", "gene_group", "coverage", "matching"}
        finding = doc["$defs"]["finding"]["properties"]
        assert finding["gnomad_entry"]["oneOf"][1] == {"type": "null"}  # null semantics are explicit
        assert doc["$defs"]["clinvar_entry"]["properties"]["condition_ids"]["type"] == ["string", "null"]


class TestRepresentativeExports:
    def test_cli_export_validates(self, example_db, tmp_path, monkeypatch):
        from click.testing import CliRunner
        from allelio import cli
        monkeypatch.setattr(cli, "AllelioDB", lambda: example_db)
        sidecar = tmp_path / "evidence.json"
        result = CliRunner().invoke(cli.analyze, [str(EXAMPLE_FILE), "--no-ai", "-o", str(tmp_path / "r.html"),
                                                  "--json-output", str(sidecar), "--detailed-trace"])
        assert result.exit_code == 0, result.output
        assert validate_evidence_file(str(sidecar)) == []
        check = CliRunner().invoke(cli.validate_evidence_command, [str(sidecar)])
        assert check.exit_code == 0 and "valid evidence JSON" in check.output

    def test_web_export_validates(self, example_db, monkeypatch):
        from fastapi.testclient import TestClient
        from allelio.web.app import app
        from allelio.web import routes

        class WebDB:
            def __new__(cls, *args, **kwargs):
                return example_db

        class Engine:
            status = "unavailable"
            model = "none"

            async def check_connection(self):
                return False

            def will_explain(self):
                return False

            async def explain_variants_batch(self, variants, progress_callback=None):
                return {}

            async def generate_summary(self, variants):
                raise RuntimeError("no model server answering")

        monkeypatch.setattr(routes, "AllelioDB", WebDB)
        monkeypatch.setattr(routes, "AIEngine", Engine)
        monkeypatch.setattr(example_db, "close", lambda: None)
        response = TestClient(app, base_url="http://127.0.0.1").post(
            "/api/analyze", files={"file": ("example.txt", EXAMPLE_FILE.read_bytes(), "text/plain")}
        )
        assert response.status_code == 200, response.text
        document = response.json()["evidence_export"]
        assert validate_evidence(document) == []
        assert document["matching"]["detailed"] is False

    def test_empty_results_validate(self, example_db):
        from allelio.analysis.lookup import analyze_variants
        from allelio.parsers.base import Variant
        variants = [Variant("rs1", "1", 100, "--"), Variant("rs99999901", "1", 1, "AA")]
        results = analyze_variants(variants, example_db)
        document = _roundtrip(build_evidence_export(results, variants, provenance_of(example_db), {}, results.stats))
        assert document["findings"] == [] and validate_evidence(document) == []
        assert validate_evidence(_roundtrip(build_evidence_export([], [], {}, None, None))) == []

    def test_legacy_or_missing_source_metadata_validates(self, example_db):
        results, stats, _, variants = run_example(example_db)
        no_provenance = _roundtrip(build_evidence_export(results, variants, {}, {}, stats))
        assert validate_evidence(no_provenance) == []
        legacy = provenance_of(example_db)
        assert all(v["release"] is None for v in legacy.values())  # fixture database records no releases
        document = _roundtrip(build_evidence_export(results, variants, legacy, {}, stats))
        assert validate_evidence(document) == []
        stripped = _roundtrip(build_evidence_export(results, variants, legacy, {}, stats))
        for entry in stripped["findings"][0]["clinvar_entries"]:
            entry["assembly"] = entry["allele_id"] = None
            entry["classification_type"] = "unknown"
        assert validate_evidence(stripped) == []


class TestFixtures:
    def test_valid_fixtures(self):
        assert validate_evidence(_load("valid_minimal")) == []
        assert validate_evidence(_load("valid_small")) == []

    @pytest.mark.parametrize("name, expected", [
        ("invalid_missing_required", "'coverage' is a required property"),
        ("invalid_wrong_type", "findings/0/significance_rank: 'high' is not of type 'number'"),
        ("invalid_unknown_enum", "allele_match: 'maybe' is not one of"),
        ("invalid_dangling_reference", "findings/0/input_ids: input_id 'input-9' does not exist in this document"),
        ("invalid_coverage_counts", "coverage/counts: {'reported': 2} does not match the listed rows {'reported': 1}"),
        ("invalid_candidate_support", "findings/0/candidate_ids: candidate-2 is 'rejected', only retained candidates support a finding"),
        ("invalid_major_version", "schema_version: '2.0' is not a 1.x document"),
    ])
    def test_invalid_fixtures_give_actionable_errors(self, name, expected):
        errors = validate_evidence(_load(name))
        assert errors and any(expected in line for line in errors), errors


class TestSemanticChecks:
    def test_conserved_counts(self):
        doc = _load("valid_small")
        doc["coverage"]["returned_findings"] = 3
        doc["matching"]["candidate_count"] = 5
        doc["matching"]["sites"][0]["candidate_count"] = 1
        errors = semantic_errors(doc)
        assert "coverage/returned_findings: 3 but 1 findings" in errors
        assert "matching/counts: sum 2 but candidate_count 5" in errors
        assert "matching/sites/0/candidate_count: 1 but 2 candidate_ids" in errors

    def test_unlisted_site_must_not_enumerate_and_ids_stay_ordered(self):
        doc = _load("valid_small")
        doc["matching"]["sites"][0]["candidates_listed"] = False
        errors = semantic_errors(doc)
        assert any("must be null when candidates are not listed" in e for e in errors)
        doc = _load("valid_small")
        doc["matching"]["candidates"].reverse()
        errors = semantic_errors(doc)
        assert any("out of order" in e for e in errors)
        doc = _load("valid_small")
        doc["findings"][0]["finding_id"] = "finding-2"
        errors = semantic_errors(doc)
        assert any("expected finding-1 (sequential)" in e for e in errors)

    def test_finding_inputs_must_share_the_rsid(self):
        doc = _load("valid_small")
        doc["inputs"][0]["rsid"] = "rs2"
        assert any("referenced inputs carry rsIDs ['rs2']" in e for e in semantic_errors(doc))

    def test_gene_group_references(self):
        doc = _load("valid_small")
        doc["gene_groups"][0]["finding_ids"] = ["finding-7"]
        doc["gene_groups"][0]["indices"] = [4]
        errors = semantic_errors(doc)
        assert any("gene_groups/0/finding_ids: finding_id 'finding-7'" in e for e in errors)
        assert "gene_groups/0/indices: index outside findings" in errors

    def test_non_object_and_unreadable_file(self, tmp_path):
        assert validate_evidence([1, 2]) == ["(document): expected a JSON object"]
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        [error] = validate_evidence_file(str(bad))
        assert error.startswith(str(bad)) and "not readable as JSON" in error


class TestCommandLine:
    def test_validate_evidence_command_reports_each_problem(self, tmp_path):
        from click.testing import CliRunner
        from allelio import cli
        path = tmp_path / "e.json"
        path.write_text(json.dumps(_load("invalid_dangling_reference")))
        result = CliRunner().invoke(cli.validate_evidence_command, [str(path)])
        assert result.exit_code == 1
        assert "1 problem(s)" in result.output and "input-9" in result.output


class TestInstalledWheel:
    @pytest.fixture(scope="class")
    def wheel(self, tmp_path_factory):
        out = tmp_path_factory.mktemp("wheel")
        build = subprocess.run(
            [sys.executable, "-m", "pip", "wheel", str(ROOT), "--no-deps", "--no-build-isolation", "-w", str(out), "-q"],
            capture_output=True, text=True,
        )
        assert build.returncode == 0, build.stderr
        [path] = out.glob("allelio-*.whl")
        return path

    def test_schema_ships_in_the_wheel_and_loads_from_it(self, wheel, tmp_path):
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            assert f"allelio/schemas/evidence-{schema.DEFAULT_SCHEMA_VERSION}.json" in names
            archive.extractall(tmp_path / "site")
        script = (
            "import json, sys; from allelio.schema import load_schema, validate_evidence, schema_path; "
            "doc = load_schema(); assert 'allelio/schemas' in str(schema_path()).replace('\\\\', '/'); "
            f"assert validate_evidence(json.load(open({str(FIXTURES / 'valid_small.json')!r}))) == []; "
            "print(doc['$id'])"
        )
        run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                             cwd=str(tmp_path), env={"PYTHONPATH": str(tmp_path / "site"), "PATH": ""})
        assert run.returncode == 0, run.stderr
        assert run.stdout.strip().endswith(f"evidence-{schema.DEFAULT_SCHEMA_VERSION}.json")
