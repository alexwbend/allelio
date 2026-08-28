"""Tests for the web interface.

The web module went unexercised long enough to accumulate a startup crash, two
missing awaits and three wrong method names, so these cover the wiring: the
routes answer, CORS is not open to the world, and the AI engine's two entry
points survive a round trip against a stubbed client.
"""

import pytest
from fastapi.testclient import TestClient

from allelio.ai.engine import AIEngine
from allelio.analysis.lookup import ClinVarEntry, GWASEntry, VariantResult
from allelio.web.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class StubClient:
    """Stands in for ollama.AsyncClient, recording what it was asked."""

    def __init__(self, reply: str = "A plain-English explanation."):
        self.reply = reply
        self.prompts = []

    async def list(self):
        return {"models": [{"name": "llama3.1:8b"}]}

    async def chat(self, model, messages, stream=False, **kwargs):
        self.prompts.append(messages[-1]["content"])
        return {"message": {"content": self.reply}}


def _variant(rsid: str = "rs429358") -> VariantResult:
    return VariantResult(
        rsid=rsid,
        genotype="CT",
        chromosome="19",
        position=44908684,
        clinvar_entries=[
            ClinVarEntry(
                rsid=rsid,
                gene="APOE",
                clinical_significance="Pathogenic",
                conditions="Alzheimer disease",
                review_status="reviewed by expert panel",
            )
        ],
        gwas_entries=[],
    )


def test_index_page_renders(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Allelio" in response.text


def test_status_reports_database_and_ai(client: TestClient) -> None:
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert "db_ready" in body
    assert "ollama_available" in body


def test_progress_starts_idle(client: TestClient) -> None:
    assert client.get("/api/progress").json()["stage"] == "idle"


def test_no_cross_origin_reads(client: TestClient) -> None:
    """A page on the open web must not be able to read a genome off localhost.

    The UI is same-origin with the API, so the app grants no origin anything.
    """
    for origin in ("https://example.com", "http://localhost:3000"):
        response = client.get("/api/status", headers={"Origin": origin})
        assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_explain_variant_uses_the_model() -> None:
    engine = AIEngine()
    engine.client = StubClient()
    engine.available = True

    explanation = await engine.explain_variant(_variant())

    assert "plain-English explanation" in explanation
    assert "rs429358" in engine.client.prompts[0]


@pytest.mark.asyncio
async def test_summary_prompt_lists_the_variants() -> None:
    """The prompt used to carry counts alone, so the model had nothing to summarise."""
    engine = AIEngine()
    engine.client = StubClient(reply="Two findings of note.")
    engine.available = True

    summary = await engine.generate_summary([_variant("rs1"), _variant("rs2")])

    assert "Two findings of note." in summary
    prompt = engine.client.prompts[0]
    assert "rs1" in prompt and "rs2" in prompt
    assert "APOE" in prompt


def test_result_cards_get_a_gene_and_a_significance() -> None:
    """The list drew every variant as "Gene: Unknown" and BENIGN, including the
    pathogenic ones, because the route sent fields the page does not read."""
    from allelio.web.routes import _gene_of, _significance_of

    variant = _variant()
    assert _gene_of(variant) == "APOE"
    assert _significance_of(variant) == "pathogenic"

    benign = VariantResult(
        rsid="rs1",
        clinvar_entries=[ClinVarEntry(rsid="rs1", clinical_significance="Benign")],
    )
    assert _significance_of(benign) == "benign"
    assert _gene_of(benign) is None


def test_conflicting_interpretations_are_not_pathogenic() -> None:
    """ClinVar's commonest ambiguous term contains the word "pathogenic"; a
    substring match painted those variants with the red badge."""
    from allelio.web.routes import _significance_of

    conflicting = VariantResult(
        rsid="rs1",
        clinvar_entries=[
            ClinVarEntry(
                rsid="rs1",
                clinical_significance="Conflicting interpretations of pathogenicity",
            )
        ],
    )
    assert _significance_of(conflicting) != "pathogenic"


@pytest.mark.asyncio
async def test_summary_prompt_names_the_gwas_gene() -> None:
    """GWASEntry calls it mapped_gene, so reading .gene left GWAS-only variants
    reaching the model with no gene at all."""
    engine = AIEngine()
    engine.client = StubClient(reply="Noted.")
    engine.available = True

    variant = VariantResult(
        rsid="rs2",
        gwas_entries=[GWASEntry(rsid="rs2", trait="Height", mapped_gene="HMGA2")],
    )
    await engine.generate_summary([variant])

    assert "HMGA2" in engine.client.prompts[0]


def test_exported_report_escapes_the_uploaded_file() -> None:
    """Genotypes are copied verbatim out of the user's file and the report is
    opened in a browser."""
    from allelio.web.routes import _generate_html_report

    html = _generate_html_report(
        {
            "summary": "<script>alert(1)</script>",
            "results": [{"rsid": "rs1", "genotype": "<img src=x onerror=alert(1)>"}],
        }
    )
    assert "<script>alert(1)</script>" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x" in html
