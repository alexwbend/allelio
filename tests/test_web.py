"""Tests for the web interface.

The web module went unexercised long enough to accumulate a startup crash, two
missing awaits and three wrong method names, so these cover the wiring: the
routes answer, CORS is not open to the world, and the AI engine's two entry
points survive a round trip against a stubbed client.
"""

import asyncio

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


def test_conflicting_classifications_get_their_own_badge() -> None:
    """ClinVar's commonest ambiguous term contains the word "pathogenic", so a
    substring match painted 130k variants with the red badge — and calling them
    a trait instead painted them green. They are neither."""
    from allelio.web.routes import _significance_of

    conflicting = VariantResult(
        rsid="rs1",
        clinvar_entries=[
            ClinVarEntry(
                rsid="rs1",
                # The term the shipped ClinVar dump actually uses.
                clinical_significance="Conflicting classifications of pathogenicity",
            )
        ],
    )
    assert _significance_of(conflicting) == "conflicting"


def test_clinvar_benign_survives_a_gwas_hit() -> None:
    """Any GWAS row used to be checked before ClinVar's benign call, so a
    variant ClinVar calls benign came out orange."""
    from allelio.web.routes import _significance_of

    variant = VariantResult(
        rsid="rs1",
        clinvar_entries=[ClinVarEntry(rsid="rs1", clinical_significance="Benign")],
        gwas_entries=[GWASEntry(rsid="rs1", trait="Height", p_value=1e-9)],
    )
    assert _significance_of(variant) == "benign"


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


def test_exported_report_escapes_its_own_header() -> None:
    """/api/export takes an arbitrary dict, so the report's own two fields are
    no more trusted than the rows."""
    from allelio.web.routes import _generate_html_report

    html = _generate_html_report(
        {"analyzed_at": "<script>alert(1)</script>", "total_variants": "<b>x</b>"}
    )
    assert "<script>alert(1)</script>" not in html
    assert "<b>x</b>" not in html


def test_strong_gwas_reads_the_smallest_p_values() -> None:
    """p_value is a float column; 6,271 rows hold 0.0, which has no exponent to
    string-slice, so the strongest associations were read as the weakest."""
    from allelio.ai.engine import AIEngine

    engine = AIEngine()
    engine.client = StubClient(reply="Noted.")
    engine.available = True

    import asyncio

    strong = VariantResult(
        rsid="rs3",
        gwas_entries=[GWASEntry(rsid="rs3", trait="Height", p_value=0.0)],
    )
    weak = VariantResult(
        rsid="rs4",
        gwas_entries=[GWASEntry(rsid="rs4", trait="Height", p_value=0.5)],
    )
    # Weak one first: only a working p-value test reorders them.
    asyncio.run(engine.generate_summary([weak, strong]))
    prompt = engine.client.prompts[0]

    assert prompt.index("rs3") < prompt.index("rs4")


def test_exported_report_carries_the_counselling_warnings() -> None:
    """The safety layer computes a warning for BRCA1/2, TP53, Lynch and APOE.
    Every consumer dropped it on the floor."""
    from allelio.web.routes import _generate_html_report

    html = _generate_html_report(
        {
            "results": [
                {
                    "rsid": "rs1",
                    # What _fallback_explanation writes: no disclaimer, because
                    # only the path where the model answered adds one.
                    "explanation": "ClinVar: Pathogenic. Gene: BRCA1.",
                    "warnings": ["Talk to a genetic counselor."],
                }
            ]
        }
    )
    assert "Talk to a genetic counselor." in html


def test_export_does_not_leave_the_report_in_the_temp_directory() -> None:
    """The report holds the user's genotypes, and the system temp directory is
    world-readable."""
    import tempfile
    from pathlib import Path

    temp_dir = Path(tempfile.gettempdir())
    before = set(temp_dir.glob("allelio_report_*"))

    client = TestClient(app)
    response = client.post("/api/export", json={"results": [{"rsid": "rs1"}]})

    assert response.status_code == 200
    assert set(temp_dir.glob("allelio_report_*")) == before


def test_upload_cannot_choose_where_it_lands() -> None:
    """The multipart filename is raw header data, and multipart is a
    CORS-safelisted content type, so any page could have posted this. The route
    writes the body to the name it is given and then unlinks it, so the damage
    is an overwrite followed by a delete."""
    import tempfile
    from pathlib import Path

    victim_dir = Path(tempfile.mkdtemp(prefix="allelio_probe_"))
    victim = victim_dir / "victim.txt"
    victim.write_text("do not touch")

    client = TestClient(app)
    client.post(
        "/api/analyze",
        files={
            "file": (
                f"{victim_dir.name}/victim.txt",
                b"rs1\t1\t1\tAA\n",
            )
        },
    )

    assert victim.exists(), "the upload deleted a file it chose the name of"
    assert victim.read_text() == "do not touch"
    victim.unlink()
    victim_dir.rmdir()


def test_a_gwas_row_is_an_association_and_nothing_stronger() -> None:
    """37,108 of the 62,057 findings on a real genome are GWAS-only. Badging
    them all RISK over-states height; badging them all TRAIT demotes type 2
    diabetes. Only 2,068 of the 553,549 GWAS rsIDs have a trait string the
    analyser can tell apart, so neither guess is available."""
    from allelio.web.routes import _significance_of

    for trait, category in [
        ("Height", "Traits"),
        ("Type 2 diabetes", "Traits"),
        ("Coronary artery disease risk", "Risk Factors"),
    ]:
        variant = VariantResult(
            rsid="rs1",
            gwas_entries=[GWASEntry(rsid="rs1", trait=trait)],
            category=category,
        )
        assert _significance_of(variant) == "association"


def test_uncertain_significance_is_not_a_trait() -> None:
    """1,236,063 ClinVar rows — the plurality — say "Uncertain significance".
    Drawn as a trait, a variant nobody can interpret reads as harmless."""
    from allelio.web.routes import _significance_of

    variant = VariantResult(
        rsid="rs1",
        clinvar_entries=[
            ClinVarEntry(rsid="rs1", clinical_significance="Uncertain significance")
        ],
    )
    assert _significance_of(variant) == "uncertain"


@pytest.mark.asyncio
async def test_explanations_give_up_and_return_what_finished() -> None:
    """Fifty variants at three at a time, each allowed 300s, can hold the
    upload open for over an hour."""
    from allelio.ai.engine import AIEngine

    engine = AIEngine()
    engine.available = True

    async def slow_or_not(result):
        if result.rsid == "rs_slow":
            await asyncio.sleep(30)
        return "done"

    engine.explain_variant = slow_or_not

    explanations = await engine.explain_variants_batch(
        [VariantResult(rsid="rs_fast"), VariantResult(rsid="rs_slow")],
        deadline=0.5,
    )

    assert explanations["rs_fast"] == "done"
    # Cut off, not dropped: an empty string would leave the card reading "No
    # explanation available", which is worse than having no model at all.
    assert "rs_slow" in explanations["rs_slow"]


def test_a_warning_is_not_printed_twice() -> None:
    """explain_variant already folds the counselling warning into the
    explanation via wrap_with_disclaimer."""
    from allelio.web.routes import _generate_html_report

    html = _generate_html_report(
        {
            "results": [
                {
                    "rsid": "rs1",
                    "explanation": "Note: talk to a genetic counselor.",
                    "warnings": ["Note: talk to a genetic counselor."],
                }
            ]
        }
    )
    assert html.count("talk to a genetic counselor.") == 1


def test_a_fallback_explanation_still_gets_its_warning() -> None:
    """explain_variant only runs wrap_with_disclaimer on the path where the
    model answered. Without Ollama every top-50 variant takes the other one."""
    from allelio.web.routes import _generate_html_report

    warning = "Genetic counseling is strongly recommended."
    wrapped = _generate_html_report(
        {"results": [{"rsid": "rs1", "explanation": f"x {warning}", "warnings": [warning]}]}
    )
    fallback = _generate_html_report(
        {"results": [{"rsid": "rs1", "explanation": "ClinVar: Pathogenic.", "warnings": [warning]}]}
    )
    assert wrapped.count(warning) == 1
    assert fallback.count(warning) == 1
