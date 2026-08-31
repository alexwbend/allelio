"""Tests for the web interface.

The web module went unexercised long enough to accumulate a startup crash, two
missing awaits and three wrong method names, so these cover the wiring: the
routes answer, CORS is not open to the world, and the AI engine's two entry
points survive a round trip against a stubbed client.
"""

import asyncio
import os
import pathlib
import subprocess
import shutil
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from allelio.ai.attribution import Explanation, attribution
from allelio.ai.engine import AIEngine
from allelio.analysis.lookup import ClinVarEntry, GWASEntry, VariantResult
from allelio.web.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1")


# The full name a run puts on the cards it wrote, as the engine builds it.
NAMED = "llama3.1:8b (Ollama at http://127.0.0.1:11434)"


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
    # Named, not just reachable: the page has to be able to print which model
    # is about to write the explanations, and where it is running.
    assert set(body["ai"]) == {
        "available",
        "model_available",
        "status",
        "provider",
        "model",
        "host",
        "error",
    }
    assert body["ai"]["provider"] == "Ollama"
    assert body["ai"]["model"]
    assert body["ai"]["host"] == "http://127.0.0.1:11434"


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
async def test_explain_uses_the_model() -> None:
    engine = AIEngine()
    engine.client = StubClient()
    engine.available = True

    written = await engine.explain(_variant())

    assert "plain-English explanation" in written.text
    assert written.model == engine.credit
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

    client = TestClient(app, base_url="http://127.0.0.1")
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

    client = TestClient(app, base_url="http://127.0.0.1")
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
        return Explanation("done", NAMED)

    engine.explain = slow_or_not

    explanations = await engine.explain_variants_batch(
        [VariantResult(rsid="rs_fast"), VariantResult(rsid="rs_slow")],
        deadline=0.5,
    )

    assert explanations["rs_fast"].text == "done"
    # Cut off, not dropped: an empty string would leave the card reading "No
    # explanation available", which is worse than having no model at all.
    assert "rs_slow" in explanations["rs_slow"].text
    # And the card the clock cut off is not credited to the model that was
    # still writing it.
    assert explanations["rs_slow"].model is None
    assert attribution(explanations).written == 1


def test_a_warning_is_not_printed_twice() -> None:
    """explain already folds the counselling warning into the
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
    """explain only runs wrap_with_disclaimer on the path where the
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


@pytest.fixture
def saved_path(tmp_path, monkeypatch):
    """Point the saved-analysis file at a temp directory, not the real one."""
    path = tmp_path / "allelio" / "last_analysis.json"
    monkeypatch.setattr("allelio.web.routes.SAVED_ANALYSIS_PATH", str(path))
    return path


def test_saving_is_opt_in(client: TestClient, saved_path) -> None:
    """Nothing reaches the disk until the user asks for it. An analysis is the
    user's genome, and a run that writes it by default is a decision made for
    them."""
    assert client.get("/api/saved").json() == {"saved": False, "saved_at": None}
    assert client.get("/api/saved/data").status_code == 404

    # The route that produces an analysis is not the route that saves one. Its
    # own outcome does not matter here; that it wrote nothing does.
    client.post("/api/analyze", files={"file": ("g.txt", b"rs1\t1\t1\tAA\n")})

    assert not saved_path.exists()
    assert client.get("/api/saved").json()["saved"] is False


def test_a_saved_analysis_comes_back_and_can_be_forgotten(
    client: TestClient, saved_path
) -> None:
    analysis = {"summary": "s", "results": [{"rsid": "rs429358"}], "total_variants": 1}

    assert client.post("/api/saved", json=analysis).status_code == 200
    assert client.get("/api/saved").json()["saved"] is True
    assert client.get("/api/saved/data").json() == analysis

    assert client.delete("/api/saved").status_code == 200
    assert not saved_path.exists()
    assert client.get("/api/saved").json()["saved"] is False
    assert client.get("/api/saved/data").status_code == 404

    # Deleting what is already gone is what the user asked for, not an error.
    assert client.delete("/api/saved").status_code == 200


def test_an_empty_body_is_not_a_saved_analysis(client: TestClient, saved_path) -> None:
    assert client.post("/api/saved", json={}).status_code == 400
    assert not saved_path.exists()


def test_an_existing_data_directory_is_left_as_it_was(
    client: TestClient, saved_path
) -> None:
    """~/.allelio normally exists already, holding the database. Silently
    re-permissioning a directory this feature does not own is not its call —
    but the file it writes there is private either way."""
    import stat

    saved_path.parent.mkdir(parents=True)
    os.chmod(saved_path.parent, 0o755)

    client.post("/api/saved", json={"results": [{"rsid": "rs1"}]})

    assert stat.S_IMODE(saved_path.parent.stat().st_mode) == 0o755
    assert stat.S_IMODE(saved_path.stat().st_mode) == 0o600


def test_the_saved_analysis_is_readable_only_by_its_owner(
    client: TestClient, saved_path
) -> None:
    """It holds the user's genotypes. The home directory is not private on a
    shared machine; the file has to be."""
    import stat

    client.post("/api/saved", json={"results": [{"rsid": "rs1", "genotype": "AA"}]})

    assert stat.S_IMODE(saved_path.stat().st_mode) == 0o600
    # Nothing existed under tmp_path, so this save is what created the directory
    # and the 0700 applies. On a real install `setup` gets there first and
    # leaves it 0755 — the test above is the one that covers that.
    assert stat.S_IMODE(saved_path.parent.stat().st_mode) == 0o700


def test_a_truncated_save_does_not_wedge_the_page(
    client: TestClient, saved_path
) -> None:
    """A crash mid-write leaves half a file. Restoring should offer nothing,
    not answer 500 forever."""
    saved_path.parent.mkdir(parents=True, exist_ok=True)
    saved_path.write_text('{"results": [{"rsid":')

    assert client.get("/api/saved/data").status_code == 404


@pytest.mark.parametrize("contents", ["[1, 2, 3]", '"hello"', "123", "null"])
def test_json_that_is_not_an_analysis_is_a_404_not_a_500(
    saved_path, contents: str
) -> None:
    """These parse, so the guarded read waves them through and they die in
    response serialisation instead — a 500 the page has no answer for."""
    saved_path.parent.mkdir(parents=True, exist_ok=True)
    saved_path.write_text(contents)

    client = TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False)
    assert client.get("/api/saved/data").status_code == 404


def test_delete_does_not_claim_a_file_it_could_not_remove(
    saved_path, monkeypatch
) -> None:
    """The page says "deleted" on any 200. Over a file holding the user's
    genotypes, that is the one lie this feature cannot afford."""
    client = TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False)
    client.post("/api/saved", json={"results": [{"rsid": "rs1"}]})

    def denied(path):
        raise PermissionError(13, "Permission denied", path)

    monkeypatch.setattr("allelio.web.routes.os.unlink", denied)

    assert client.delete("/api/saved").status_code == 500
    assert saved_path.exists(), "the test itself failed to keep the file"


def test_a_failed_save_keeps_the_previous_one(saved_path, monkeypatch) -> None:
    """The write is a temp file plus a rename for this reason: the user pays
    half an hour for each analysis, so a bad save must not eat the good one."""
    client = TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False)
    good = {"summary": "the one that finished", "results": []}
    assert client.post("/api/saved", json=good).status_code == 200

    # Out of disk part-way through the dump — the case the rename exists for,
    # and the one where the temp file already has bytes in it.
    import json as json_module

    real_dump = json_module.dump

    def full_disk(obj, fp):
        fp.write("{" * 100)
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("allelio.web.routes.json.dump", full_disk)

    assert client.post("/api/saved", json={"summary": "the one that ran out"}).status_code == 500

    # Put json.dump back and nothing else: monkeypatch.undo() would also drop
    # the saved_path fixture's patch and send the read at the real home
    # directory.
    monkeypatch.setattr("allelio.web.routes.json.dump", real_dump)
    assert client.get("/api/saved/data").json() == good
    assert list(saved_path.parent.glob(".last_analysis_*")) == []


def test_a_rebound_domain_cannot_read_the_saved_genome(saved_path) -> None:
    """Binding to 127.0.0.1 is not a boundary. A page on a domain whose DNS
    re-resolves to 127.0.0.1 is same-origin to the browser, so CORS never
    applies; the Host header is the only thing that tells the two apart."""
    client = TestClient(app, base_url="http://attacker.example")

    assert client.get("/api/saved").status_code == 400
    assert client.get("/api/saved/data").status_code == 400
    assert client.post("/api/saved", json={"results": []}).status_code == 400
    assert client.delete("/api/saved").status_code == 400

    # Starlette strips the port before matching, so a port on the URL changes
    # nothing — which is exactly why no allow-list entry carries one.
    assert TestClient(app, base_url="http://127.0.0.1:8080").get("/api/saved").status_code == 200
    assert TestClient(app, base_url="http://localhost").get("/api/saved").status_code == 200


@pytest.mark.parametrize(
    "host,expected",
    [
        # A bind address is never a Host header anyone types, and starlette
        # strips the port by splitting on ":", so no IPv6 literal can match.
        # None of these belong on the list; localhost is how you reach them.
        ("0.0.0.0", ["localhost", "127.0.0.1"]),
        ("::", ["localhost", "127.0.0.1"]),
        ("::1", ["localhost", "127.0.0.1"]),
        # inet_aton takes all of these as "every interface", and so does the
        # bind — comparing against the dotted quad alone would let them past.
        ("0", ["localhost", "127.0.0.1"]),
        ("0.0", ["localhost", "127.0.0.1"]),
        ("0x0", ["localhost", "127.0.0.1"]),
        # asyncio turns an empty host into a passive getaddrinfo, which binds
        # every interface as surely as 0.0.0.0 does.
        ("", ["localhost", "127.0.0.1"]),
        ("127.0.0.1", ["localhost", "127.0.0.1"]),
        # A real name the operator can browse to does belong on it — lowercased,
        # because that is how the browser will send it.
        ("192.168.1.50", ["localhost", "127.0.0.1", "192.168.1.50"]),
        ("MyBox.local", ["localhost", "127.0.0.1", "mybox.local"]),
    ],
)
def test_only_hosts_a_browser_can_actually_send_go_on_the_allow_list(host, expected) -> None:
    from click.testing import CliRunner

    from allelio.cli import allelio

    with mock.patch.dict(os.environ, {}, clear=False):
        # An empty value has to count as unset: app.py drops empties and falls
        # back, so leaving it would 400 every request with no warning printed.
        os.environ["ALLELIO_ALLOWED_HOSTS"] = ""
        with mock.patch("uvicorn.run") as run:
            result = CliRunner().invoke(allelio, ["serve", "--host", host, "--port", "9999"])
        assert run.called
        assert os.environ["ALLELIO_ALLOWED_HOSTS"].split(",") == expected
        # Rich wraps to the terminal width, so match on collapsed whitespace.
        # A host that could not go on the list gets told where to browse
        # instead; one that did needs no warning it would learn to ignore.
        printed = " ".join(result.output.split())
        browsable = host in ("127.0.0.1", "192.168.1.50", "MyBox.local")
        assert ("browse to localhost" in printed) != browsable
        # And the URL it tells them to open is one that will actually answer.
        assert (f"http://{host}:9999" in printed) == browsable


def test_a_users_own_host_list_is_left_alone() -> None:
    from click.testing import CliRunner

    from allelio.cli import allelio

    with mock.patch.dict(os.environ, {"ALLELIO_ALLOWED_HOSTS": "Allelio.Local"}, clear=False):
        with mock.patch("uvicorn.run"):
            CliRunner().invoke(allelio, ["serve", "--host", "0.0.0.0", "--port", "9999"])
        assert os.environ["ALLELIO_ALLOWED_HOSTS"] == "Allelio.Local"

    import importlib

    import allelio.web.app as app_module

    with mock.patch.dict(os.environ, {"ALLELIO_ALLOWED_HOSTS": "Allelio.Local"}, clear=False):
        try:
            hosts = importlib.reload(app_module).ALLOWED_HOSTS
        finally:
            os.environ.pop("ALLELIO_ALLOWED_HOSTS", None)
            importlib.reload(app_module)

    # Lowercased, because a browser sends the host lowercased and starlette
    # compares it exactly. Loopback stays on: naming a LAN address should not
    # lock the operator out of the machine the server is running on.
    assert hosts == ["localhost", "127.0.0.1", "allelio.local"]


@pytest.mark.parametrize(
    "bad",
    [
        # A "*" anywhere past the first character.
        "192.168.*.5",
        # And a leading one that is not the "*." of a subdomain wildcard: a
        # forgotten dot, which starlette rejects on its own second assert.
        "*example.com",
    ],
)
def test_a_typo_in_the_host_list_fails_at_startup_not_mid_run(monkeypatch, bad) -> None:
    """Starlette only checks its patterns when the stack is first built, which is
    on the first request — long after the URL has been printed and opened — and
    it checks with an assert, which -O removes. Hence our own check at import."""
    import importlib

    import allelio.web.app as app_module

    monkeypatch.setenv("ALLELIO_ALLOWED_HOSTS", bad)
    try:
        with pytest.raises(ValueError, match="wildcard host"):
            importlib.reload(app_module)
    finally:
        # Put the module back whether or not the check fired: a failure here
        # would otherwise hand every later test an app built from the bad list.
        monkeypatch.delenv("ALLELIO_ALLOWED_HOSTS")
        importlib.reload(app_module)


# --- Choosing a model server -------------------------------------------------
#
# The engine will talk to Ollama or to any OpenAI-compatible server, and the
# prompts it sends carry the variant they are asking about. So the address is a
# privacy boundary, not a preference, and these cover both halves: that it only
# ever resolves to this machine, and that whatever it does end up using can be
# named on screen.


class FakeHttpx:
    """Stands in for the httpx module inside the engine, answering from a handler.

    Patched in as `engine.httpx` rather than onto httpx itself, so the test
    client the rest of this file uses is left alone.
    """

    def __init__(self, handler):
        self._handler = handler
        self.built = []

    def AsyncClient(self, **kwargs):
        import httpx as real

        self.built.append(kwargs)

        return real.AsyncClient(transport=real.MockTransport(self._handler), **kwargs)


def _openai_server(
    monkeypatch,
    served=("qwen2.5-14b-instruct",),
    reply="Plain English.",
    lists=True,
    answers_anything=False,
):
    """Wire the engine to a stubbed OpenAI-compatible server; returns the requests.

    Honest by default, which the first version of this was not: both real
    servers answer a completion for a model they do not serve with a 404 and
    {"error": {"message": "model 'x' not found"}} — measured, Ollama in 2.2 ms
    and llama-swap in 0.9 ms. A stub that answers anything hides the only
    evidence there is that a name was wrong.

    lists=False is a bare llama.cpp: it serves completions and has no
    /v1/models at all. answers_anything=True is the server that ignores the
    field it was sent, which is the case the attribution rule exists for.
    """
    import httpx as real

    from allelio.ai import engine as engine_module

    seen = []

    def handler(request: "real.Request") -> "real.Response":
        seen.append(request)
        if request.url.path.endswith("/models"):
            if not lists:
                return real.Response(
                    404, json={"error": {"message": "no /v1/models here"}}
                )
            return real.Response(200, json={"data": [{"id": name} for name in served]})
        if request.url.path.endswith("/chat/completions"):
            import json as _json

            asked = _json.loads(request.content).get("model")
            if not answers_anything and asked not in served:
                return real.Response(
                    404, json={"error": {"message": f"model '{asked}' not found"}}
                )
            return real.Response(
                200, json={"choices": [{"message": {"content": reply}}]}
            )
        return real.Response(404)

    monkeypatch.setattr(engine_module, "httpx", FakeHttpx(handler))
    return seen


@pytest.mark.parametrize(
    "url,pinned",
    [
        ("http://127.0.0.1:1234/v1", "http://127.0.0.1:1234/v1"),
        # The name is replaced by what it resolved to, so the request cannot be
        # sent somewhere the check never saw.
        ("http://localhost:11434", "http://127.0.0.1:11434"),
        ("http://[::1]:8080/v1", "http://[::1]:8080/v1"),
        # All of 127/8 is this machine, not just the .1.
        ("http://127.0.0.2:9999/v1", "http://127.0.0.2:9999/v1"),
        ("https://127.0.0.1:8443/v1", "https://127.0.0.1:8443/v1"),
        # Spellings of 127.0.0.1 that a checker comparing strings would miss.
        ("http://2130706433/v1", "http://127.0.0.1/v1"),
        ("http://127.1/v1", "http://127.0.0.1/v1"),
        # Userinfo is dropped with the name it was attached to.
        ("http://api.openai.com@127.0.0.1/v1", "http://127.0.0.1/v1"),
    ],
)
def test_a_model_server_on_this_machine_is_accepted(url: str, pinned: str) -> None:
    from allelio.ai.engine import pin_to_loopback

    assert pin_to_loopback(url, "ALLELIO_OPENAI_BASE") == pinned


@pytest.mark.parametrize(
    "url,because",
    [
        # The whole point: a hosted endpoint in this setting reads the genome.
        ("http://104.18.7.1/v1", "not this machine"),
        ("http://192.168.1.50:1234/v1", "not this machine"),
        ("http://[2001:4860:4860::8888]/v1", "not this machine"),
        # Binds everywhere, resolves to nothing in particular. Say 127.0.0.1.
        ("http://0.0.0.0:1234/v1", "not this machine"),
        ("localhost:1234", "is not a URL"),
        ("ftp://127.0.0.1/v1", "is not a URL"),
        ("file:///etc/passwd", "is not a URL"),
        ("http://", "is not a URL"),
        ("", "is not a URL"),
    ],
)
def test_a_model_server_anywhere_else_is_refused(url: str, because: str) -> None:
    from allelio.ai.engine import pin_to_loopback

    with pytest.raises(ValueError, match=because):
        pin_to_loopback(url, "ALLELIO_OPENAI_BASE")


def _resolving_to(monkeypatch, *addresses):
    """Make every name resolve to exactly these addresses, resolver or no resolver."""
    import socket as socket_module

    from allelio.ai import engine as engine_module

    def fake_getaddrinfo(host, port, *args, **kwargs):
        if not addresses:
            raise socket_module.gaierror(-2, "Name or service not known")
        return [
            (socket_module.AF_INET, socket_module.SOCK_STREAM, 6, "", (a, port or 0))
            for a in addresses
        ]

    monkeypatch.setattr(engine_module.socket, "getaddrinfo", fake_getaddrinfo)


def test_a_name_that_resolves_to_nothing_is_refused(monkeypatch) -> None:
    """Not resolving is not resolving to 127.0.0.1.

    Asserted against a stubbed resolver rather than a .invalid name, because a
    hijacking ISP resolver answers those with an ad server.
    """
    from allelio.ai.engine import pin_to_loopback

    _resolving_to(monkeypatch)

    with pytest.raises(ValueError, match="does not resolve"):
        pin_to_loopback("http://nowhere.invalid:1234/v1", "ALLELIO_OPENAI_BASE")


def test_one_public_answer_out_of_four_refuses_the_whole_name(monkeypatch) -> None:
    """A DNS-rebinding name answers 127.0.0.1 and its own address in one reply.

    Accepting it because a loopback address is in there would ship the genome
    on whichever answer the connection happened to pick.
    """
    from allelio.ai.engine import pin_to_loopback

    _resolving_to(monkeypatch, "127.0.0.1", "127.0.0.1", "127.0.0.1", "104.18.7.1")

    with pytest.raises(ValueError, match="104.18.7.1"):
        pin_to_loopback("http://rebind.example:1234/v1", "ALLELIO_OPENAI_BASE")


def test_ipv4_is_preferred_over_the_ipv6_answer(monkeypatch) -> None:
    """macOS answers "localhost" with ::1 first, and Ollama does not bind ::1."""
    from allelio.ai.engine import pin_to_loopback

    import socket as socket_module

    from allelio.ai import engine as engine_module

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (socket_module.AF_INET6, socket_module.SOCK_STREAM, 6, "", ("::1", port, 0, 0)),
            (socket_module.AF_INET, socket_module.SOCK_STREAM, 6, "", ("127.0.0.1", port)),
        ]

    monkeypatch.setattr(engine_module.socket, "getaddrinfo", fake_getaddrinfo)

    assert pin_to_loopback("http://localhost:11434", "host") == "http://127.0.0.1:11434"


def test_the_ollama_client_neither_redirects_nor_proxies(monkeypatch) -> None:
    """Two httpx defaults that each walk a prompt off the checked address.

    ollama's client turns redirect-following on; httpx trusts HTTP_PROXY,
    ALL_PROXY, .netrc, and on macOS the proxy in System Settings, which an
    MDM-managed laptop ships with. Pinning the host counts for nothing if the
    connection is handed to a proxy afterwards.
    """
    monkeypatch.setenv("ALL_PROXY", "http://corp.proxy.example:8080")
    monkeypatch.setenv("HTTP_PROXY", "http://corp.proxy.example:8080")

    engine = AIEngine()

    assert engine.client._client.follow_redirects is False
    assert _proxied(engine.client._client) is False
    # ollama-python injects OLLAMA_API_KEY as a bearer token regardless of
    # trust_env. There is nowhere for a key to go when the only reachable server
    # is on this machine — it could only be handed to whatever got to :11434
    # first. Set here rather than relying on the developer's shell not having one.
    monkeypatch.setenv("OLLAMA_API_KEY", "sk-a-real-ollama-cloud-key")

    engine = AIEngine()

    assert "authorization" not in {k.lower() for k in engine.client._client.headers}
    assert "sk-a-real-ollama-cloud-key" not in str(engine.client._client.headers)


def test_the_ollama_environment_cannot_move_the_address(monkeypatch) -> None:
    """host= is always passed, so OLLAMA_HOST never gets a say."""
    monkeypatch.setenv("OLLAMA_HOST", "http://evil.example.com:11434")

    engine = AIEngine()

    assert engine.host == "http://127.0.0.1:11434"
    # engine.host is what the guard decided; base_url is where the request goes.
    assert str(engine.client._client.base_url).startswith("http://127.0.0.1:11434")


def _proxied(client) -> bool:
    """Whether this httpx client would hand the connection to a proxy."""
    import httpx as real

    transport = client._transport_for_url(real.URL("http://127.0.0.1:11434/x"))
    return type(transport._pool).__name__ != "AsyncConnectionPool"


def test_httpx_would_have_proxied_it(monkeypatch) -> None:
    """The control for the assertion above: without trust_env=False it leaks."""
    import httpx as real

    monkeypatch.setenv("ALL_PROXY", "http://corp.proxy.example:8080")
    monkeypatch.setenv("HTTP_PROXY", "http://corp.proxy.example:8080")

    assert _proxied(real.AsyncClient()) is True


@pytest.mark.asyncio
async def test_the_openai_client_neither_redirects_nor_proxies(monkeypatch) -> None:
    """Same two defaults, on the path that was added by this change."""
    # Serving the configured model: the engine does not send a prompt to a
    # server whose listing says it has not got it, so an empty listing here
    # would mean the second client is never built and this would pass for the
    # wrong reason.
    fake = FakeHttpx(
        lambda request: __import__("httpx").Response(
            200, json={"data": [{"id": "llama3.1:8b"}]}
        )
    )

    from allelio.ai import engine as engine_module

    monkeypatch.setattr(engine_module, "httpx", fake)
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")

    engine = AIEngine()
    await engine.check_connection()
    engine.available = True
    await engine.explain(_variant())

    # Both calls: the listing and the prompt.
    assert len(fake.built) == 2
    for kwargs in fake.built:
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False


def test_the_refusal_names_the_setting_and_the_reason() -> None:
    """A refusal nobody can act on is a bug report waiting to be filed."""
    from allelio.ai.engine import pin_to_loopback

    with pytest.raises(ValueError) as caught:
        pin_to_loopback("http://104.18.7.1/v1", "ALLELIO_OPENAI_BASE")

    message = str(caught.value)
    assert "ALLELIO_OPENAI_BASE" in message
    assert "104.18.7.1" in message
    assert "127.0.0.1" in message


def test_a_remote_address_is_refused_by_the_engine_itself(monkeypatch) -> None:
    """Not merely unused — construction fails, so no code path can reach it."""
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://104.18.7.1/v1")

    with pytest.raises(ValueError, match="not this machine"):
        AIEngine()


def test_ollama_is_still_the_default(monkeypatch) -> None:
    engine = AIEngine()

    assert engine.provider == "Ollama"
    # The name it was written with is gone: what is connected to is what was checked.
    assert engine.host == "http://127.0.0.1:11434"
    assert engine.model == "llama3.1:8b"


def test_the_openai_base_switches_provider(monkeypatch) -> None:
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")

    engine = AIEngine()

    assert engine.provider == "OpenAI-compatible"
    assert engine.host == "http://127.0.0.1:1234/v1"


@pytest.mark.asyncio
async def test_an_unnamed_model_is_taken_from_a_server_holding_one(monkeypatch) -> None:
    """A server holding one model calls it whatever it likes.

    Reporting the built-in Ollama default there would name a model that is not
    running and never was.
    """
    _openai_server(monkeypatch, served=["qwen2.5-14b-instruct"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")

    engine = AIEngine()
    assert await engine.check_connection() is True

    assert engine.model == "qwen2.5-14b-instruct"


@pytest.mark.asyncio
async def test_a_server_holding_several_models_is_not_guessed_at(monkeypatch) -> None:
    """llama-swap lists a dozen. Taking whichever came first would load an 80B
    coder model to explain a genome, and print its name as though it had been
    chosen."""
    _openai_server(monkeypatch, served=["Qwen3-Coder-80B", "gemma3:12b", "llama3.1:8b"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")

    engine = AIEngine()
    await engine.check_connection()

    assert engine.model == "llama3.1:8b"  # the default, untouched
    # And the menu is kept, so the CLI can print it instead of "ollama pull".
    assert engine.served_models == ["Qwen3-Coder-80B", "gemma3:12b", "llama3.1:8b"]


@pytest.mark.asyncio
async def test_a_named_model_survives_the_connection(monkeypatch) -> None:
    _openai_server(monkeypatch, served=["qwen2.5-14b-instruct"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("ALLELIO_MODEL", "mistral-nemo:12b")

    engine = AIEngine()
    await engine.check_connection()

    assert engine.model == "mistral-nemo:12b"


@pytest.mark.asyncio
async def test_ollama_keeps_the_documented_default(monkeypatch) -> None:
    """Ollama holds many models; the first one it lists is not a choice."""
    engine = AIEngine()
    engine.client = StubClient()

    await engine.check_connection()

    assert engine.model == "llama3.1:8b"


def test_the_environment_names_the_model_for_ollama_too(monkeypatch) -> None:
    monkeypatch.setenv("ALLELIO_MODEL", "mistral-nemo:12b")

    assert AIEngine().model == "mistral-nemo:12b"
    # An explicit argument still outranks it.
    assert AIEngine(model="gemma2:9b").model == "gemma2:9b"


@pytest.mark.asyncio
async def test_explanations_go_out_over_chat_completions(monkeypatch) -> None:
    """The wire format, and the header that is deliberately absent from it."""
    import json

    seen = _openai_server(
        monkeypatch,
        served=("mistral-nemo:12b",),
        reply="A plain-English explanation.",
    )
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("ALLELIO_MODEL", "mistral-nemo:12b")

    engine = AIEngine()
    engine.available = True
    explanation = (await engine.explain(_variant())).text

    assert "plain-English explanation" in explanation
    posted = [r for r in seen if r.method == "POST"]
    assert [str(r.url) for r in posted] == ["http://127.0.0.1:1234/v1/chat/completions"]
    body = json.loads(posted[0].content)
    assert body["model"] == "mistral-nemo:12b"
    assert "rs429358" in body["messages"][-1]["content"]
    # No key is sent because there is nowhere to send one: the only servers this
    # can reach are on this machine, and a key would mean it had left.
    assert all("authorization" not in r.headers for r in seen)


def _serving(*names):
    """A stub client whose list() reports exactly these models."""
    client = StubClient()

    async def list_models():
        return {"models": [{"model": name} for name in names]}

    client.list = list_models
    return client


@pytest.mark.asyncio
async def test_a_different_tag_is_not_the_model_you_asked_for() -> None:
    """"llama3.1:8b" used to be answered yes by a box holding only the 70b.

    The run then died at the first explanation instead of here, where the CLI
    can still say which model to pull.
    """
    engine = AIEngine(model="llama3.1:8b")

    engine.client = _serving("llama3.1:70b")
    await engine.check_connection()
    assert engine.check_model_available() is False

    # A quantisation of the model you asked for is a different model, and this
    # is the pair that tells a whole-name comparison from a substring one.
    engine.client = _serving("llama3.1:8b-instruct-q8_0")
    await engine.check_connection()
    assert engine.check_model_available() is False

    engine.client = _serving("llama3.1:8b", "llama3.1:70b")
    await engine.check_connection()
    assert engine.check_model_available() is True


@pytest.mark.asyncio
async def test_a_bare_model_name_means_latest() -> None:
    """Ollama's own shorthand, so asking for it should not be a miss."""
    engine = AIEngine(model="llama3.1")
    engine.client = _serving("llama3.1:latest")
    await engine.check_connection()

    assert engine.check_model_available() is True


@pytest.mark.asyncio
async def test_the_model_check_costs_no_second_request() -> None:
    """It reads the listing check_connection already fetched.

    Asking twice used to mean a second call on a client bound to the first
    call's event loop, which answered "not on that server" about a model that
    was sitting right there.
    """
    calls = []

    engine = AIEngine()
    engine.client = _serving("llama3.1:8b")
    listing = engine.client.list

    async def counted():
        calls.append(1)
        return await listing()

    engine.client.list = counted
    await engine.check_connection()

    assert engine.check_model_available() is True
    assert engine.check_model_available() is True
    assert len(calls) == 1


def test_status_names_the_model_and_where_it_runs(monkeypatch) -> None:
    _openai_server(monkeypatch, served=["qwen2.5-14b-instruct"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")

    body = TestClient(app, base_url="http://127.0.0.1").get("/api/status").json()

    assert body["ai"] == {
        "available": True,
        "model_available": True,
        "status": "serving",
        "provider": "OpenAI-compatible",
        "model": "qwen2.5-14b-instruct",
        "host": "http://127.0.0.1:1234/v1",
        "error": None,
    }


def test_status_does_not_call_a_missing_model_ready(monkeypatch) -> None:
    """Reachable is not loaded, and the dot on the page follows the model."""
    _openai_server(monkeypatch, served=["gemma3:12b", "Qwen3-Coder-80B"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")

    body = TestClient(app, base_url="http://127.0.0.1").get("/api/status").json()

    assert body["ai"]["available"] is True
    assert body["ai"]["model_available"] is False
    assert body["ai"]["model"] == "llama3.1:8b"


def test_status_says_why_rather_than_reporting_a_disconnection(monkeypatch) -> None:
    """"Disconnected" would send them hunting for a crash that never happened."""
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://104.18.7.1/v1")

    body = TestClient(app, base_url="http://127.0.0.1").get("/api/status").json()

    assert body["ai"]["available"] is False
    assert "not this machine" in body["ai"]["error"]
    # And the rest of the page still works: the database half is unaffected.
    assert "db_ready" in body


def test_a_refused_address_stops_the_upload_before_the_work(monkeypatch) -> None:
    """Half an hour of analysis is a long time to wait for a settings error."""
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://104.18.7.1/v1")

    response = TestClient(app, base_url="http://127.0.0.1").post(
        "/api/analyze",
        files={"file": ("genome.txt", b"rs1\t1\t100\tAA\n", "text/plain")},
    )

    assert response.status_code == 400
    assert "not this machine" in response.json()["detail"]


# --- `allelio info` and `allelio analyze`, on the model half -----------------


def _cli_info(monkeypatch):
    """Run `allelio info` and hand back its output, collapsed to one line.

    Rich wraps to the terminal width and puts a newline wherever it likes, so
    every assertion below is against collapsed whitespace.
    """
    from click.testing import CliRunner

    from allelio.cli import allelio

    result = CliRunner().invoke(allelio, ["info"])
    return " ".join(result.output.split())


def test_info_names_the_model_and_where_it_runs(monkeypatch) -> None:
    _openai_server(monkeypatch, served=["Qwen3.6-35B-A3B"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")

    printed = _cli_info(monkeypatch)

    assert "OpenAI-compatible answering at http://127.0.0.1:1234/v1" in printed
    assert "Qwen3.6-35B-A3B" in printed


def test_info_refuses_a_model_server_that_is_not_on_this_machine(monkeypatch) -> None:
    """The refusal has to reach the person, not just the exception handler."""
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://104.18.7.1/v1")

    printed = _cli_info(monkeypatch)

    assert "ALLELIO_OPENAI_BASE" in printed
    assert "not this machine" in printed
    # And nothing was contacted, so nothing can be reported as answering.
    assert "answering at" not in printed


def test_info_prints_the_menu_rather_than_an_ollama_pull(monkeypatch) -> None:
    """`ollama pull Qwen3.6-35B` cannot work against llama-swap.

    A server serving a dozen models under its own names gets its menu printed;
    only Ollama gets told to pull.
    """
    _openai_server(monkeypatch, served=["Qwen3.6-35B-A3B", "gemma3:12b"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")

    printed = _cli_info(monkeypatch)

    assert "llama3.1:8b is not on that server" in printed
    assert "That server offers: Qwen3.6-35B-A3B, gemma3:12b" in printed
    assert "ALLELIO_MODEL" in printed
    assert "ollama pull" not in printed


def test_info_tells_an_ollama_user_to_pull(monkeypatch) -> None:
    from allelio.ai import engine as engine_module

    monkeypatch.setattr(
        engine_module, "AsyncClient", lambda **kwargs: _serving("gemma2:9b")
    )

    printed = _cli_info(monkeypatch)

    assert "Ollama answering at http://127.0.0.1:11434" in printed
    assert "ollama pull llama3.1:8b" in printed


def test_info_says_a_missing_model_server_is_optional(monkeypatch) -> None:
    """Allelio works without one, and the README promises so."""
    from allelio.ai import engine as engine_module

    class Silent:
        async def list(self):
            raise ConnectionRefusedError("nothing there")

    monkeypatch.setattr(engine_module, "AsyncClient", lambda **kwargs: Silent())

    printed = _cli_info(monkeypatch)

    assert "No answer from Ollama at http://127.0.0.1:11434" in printed
    assert "optional" in printed


def _analyze(monkeypatch, tmp_path, *extra, variants=None):
    """Run `allelio analyze` over stubbed variants with a stubbed lookup."""
    from click.testing import CliRunner

    from allelio.cli import allelio

    raw = tmp_path / "genome.txt"
    raw.write_text("# rsid\tchromosome\tposition\tgenotype\nrs429358\t19\t44908684\tCT\n")

    import allelio.cli as cli_module

    class FakeDB:
        def is_initialized(self):
            return True

        def version(self):
            return "test"

        def close(self):
            pass

    monkeypatch.setattr(cli_module, "AllelioDB", lambda *a, **k: FakeDB())
    monkeypatch.setattr(cli_module, "parse_genotype_file", lambda path: [_variant()])
    found = variants if variants is not None else [_variant()]
    monkeypatch.setattr(cli_module, "analyze_variants", lambda v, **kwargs: found)
    return CliRunner().invoke(
        allelio, ["analyze", str(raw), "--output", str(tmp_path / "r.html"), *extra]
    )


def test_analyze_refuses_a_model_server_that_is_not_on_this_machine(
    monkeypatch, tmp_path
) -> None:
    """It aborts rather than falling back.

    Half an hour of analysis that ends in a report is not the place to discover
    the model address was rejected, and silently dropping the explanations would
    hide that the setting was ignored.
    """
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://104.18.7.1/v1")

    result = _analyze(monkeypatch, tmp_path)

    assert result.exit_code != 0
    printed = " ".join(result.output.split())
    assert "ALLELIO_OPENAI_BASE" in printed
    assert "not this machine" in printed


def test_analyze_does_not_credit_a_model_that_never_answered(
    monkeypatch, tmp_path
) -> None:
    """explain answers with the variant's own data when the call fails.

    That text reads like an explanation and is not one, so counting it would put
    a model's name on a report it had no part in writing.
    """
    from allelio.ai import engine as engine_module

    class Silent:
        async def list(self):
            raise ConnectionRefusedError("nothing there")

        async def chat(self, **kwargs):
            raise ConnectionRefusedError("nothing there")

    monkeypatch.setattr(engine_module, "AsyncClient", lambda **kwargs: Silent())

    result = _analyze(monkeypatch, tmp_path)
    printed = " ".join(result.output.split())

    assert "Generated" not in printed
    # Nothing answered, so no prompt was sent and "no explanations generated"
    # would be describing the wrong thing.
    assert "No answer from Ollama at http://127.0.0.1:11434" in printed
    assert "Continuing without explanations" in printed
    # And the report, which is the thing that gets kept and shown to a doctor,
    # does not carry a model's name over pages it had no part in writing.
    report = (tmp_path / "r.html").read_text()
    assert "llama3.1:8b" not in report
    assert "AI Model: none" in report


@pytest.mark.asyncio
async def test_a_model_server_does_not_get_to_name_itself_in_markup(monkeypatch) -> None:
    """The adopted name is printed on the page and written into the report.

    A server on 127.0.0.1 is not automatically a trusted one — anything on this
    machine can bind a port — so a name it made up is not adopted at all.
    """
    _openai_server(monkeypatch, served=['<img src=x onerror=alert(1)>'])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")

    engine = AIEngine()
    assert await engine.check_connection() is True

    assert engine.model == "llama3.1:8b"


@pytest.mark.asyncio
async def test_the_names_real_servers_use_are_still_adopted(monkeypatch) -> None:
    """The guard has to let through what llama.cpp and LM Studio actually serve."""
    _openai_server(monkeypatch, served=["hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")

    engine = AIEngine()
    await engine.check_connection()

    assert engine.model == "hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M"


def test_the_report_escapes_the_model_name() -> None:
    """The name is the server's own, and the report is a file people open.

    It rides on the card now rather than arriving in the metadata, so it
    reaches three sinks — the footer, the note, and the heading over the
    explanation itself — and all three escape it.
    """
    from allelio.report import generate_html_report

    hostile = '<img src=x onerror=alert(1)>'
    html = generate_html_report(
        [_variant()],
        {"rs429358": Explanation("Plain English.", hostile)},
        "",
        {"generated_at": "now"},
    )

    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "1 of 1 variants analyzed with &lt;img" in html
    assert "AI Analysis — &lt;img" in html


@pytest.mark.asyncio
async def test_the_bridge_message_names_the_provider_it_actually_used(
    monkeypatch,
) -> None:
    """"Is Ollama running? (ollama serve)" is a wrong answer against llama-swap."""
    from allelio.ai.explanations import generate_explanation

    class Silent:
        async def list(self):
            raise ConnectionRefusedError("nothing there")

    def handler(request):
        raise ConnectionRefusedError("nothing there")

    from allelio.ai import engine as engine_module

    monkeypatch.setattr(engine_module, "httpx", FakeHttpx(handler))
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")

    with pytest.raises(RuntimeError) as caught:
        await generate_explanation(_variant())

    message = str(caught.value)
    assert "OpenAI-compatible at http://127.0.0.1:1234/v1" in message
    assert "ollama" not in message.lower()


@pytest.mark.asyncio
async def test_the_bridge_lists_what_the_server_does_have(monkeypatch) -> None:
    from allelio.ai.explanations import generate_explanation

    _openai_server(monkeypatch, served=["Qwen3.6-35B-A3B", "gemma3:12b"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("ALLELIO_MODEL", "llama3.1:8b")

    with pytest.raises(RuntimeError, match="Qwen3.6-35B-A3B, gemma3:12b"):
        await generate_explanation(_variant())


def test_an_ollama_host_off_this_machine_is_refused() -> None:
    """The guard is on the constructor, so the ollama path is held to it too."""
    with pytest.raises(ValueError, match="not this machine"):
        AIEngine(host="http://104.18.7.1:11434")


def test_analyze_credits_the_model_that_did_answer(monkeypatch, tmp_path) -> None:
    """The other half of the tally: a model that wrote the pages gets named."""
    from allelio.ai import engine as engine_module

    class Answering:
        async def list(self):
            return {"models": [{"model": "llama3.1:8b"}]}

        async def chat(self, **kwargs):
            return {"message": {"content": "A plain-English explanation."}}

    monkeypatch.setattr(engine_module, "AsyncClient", lambda **kwargs: Answering())

    result = _analyze(monkeypatch, tmp_path)
    printed = " ".join(result.output.split())

    assert "Generated 1 AI explanations" in printed
    report = (tmp_path / "r.html").read_text()
    assert "llama3.1:8b (Ollama at http://127.0.0.1:11434)" in report


def test_the_same_address_written_two_ways_gets_the_same_answer() -> None:
    """IPv6Address.is_loopback only learned about ::ffff:127.0.0.1 in 3.13.

    This package claims 3.9, so the answer is decided here rather than by
    whichever Python is installed.
    """
    from allelio.ai.engine import pin_to_loopback

    assert (
        pin_to_loopback("http://[::ffff:127.0.0.1]:1234/v1", "ALLELIO_OPENAI_BASE")
        == "http://127.0.0.1:1234/v1"
    )
    # And the wrapping does not launder a public address into a local one.
    with pytest.raises(ValueError, match="not this machine"):
        pin_to_loopback("http://[::ffff:104.18.7.1]:1234/v1", "ALLELIO_OPENAI_BASE")


@pytest.mark.asyncio
async def test_the_batch_counts_what_came_back_not_what_finished() -> None:
    """A task can finish just as the clock runs out and have its answer dropped.

    What puts a model's name on a card is the card, so a card that was never
    handed back cannot carry one — and a previous run cannot lend it one
    either. The engine keeps no count between runs to go stale; this asserts
    there is nowhere for one to hide.
    """
    engine = AIEngine()
    engine.available = True
    engine.client = StubClient()

    explanations = await engine.explain_variants_batch(
        [_variant("rs1"), _variant("rs2")], max_concurrent=2
    )

    assert len(explanations) == 2
    assert attribution(explanations).written == 2
    assert not hasattr(engine, "explained")

    # A second run answers for its own cards and nothing else.
    again = await engine.explain_variants_batch([_variant("rs3")])
    assert attribution(again) == (attribution(again).model, 1, 1)


@pytest.mark.asyncio
async def test_each_card_carries_its_own_reason_for_having_no_model() -> None:
    """Three calls run at a time and the engine has one slot for the last error.

    A card asking why it has no explanation used to get whichever answer landed
    last, so a timed-out variant was reported as "model not found" because
    another variant failed that way a moment later.
    """
    engine = AIEngine()
    engine.available = True

    class DifferentFailures:
        async def chat(self, model, messages, **kwargs):
            if "rs_missing" in messages[-1]["content"]:
                raise RuntimeError("model 'x' not found")
            raise asyncio.TimeoutError()

    engine.client = DifferentFailures()

    written = await engine.explain_variants_batch(
        [_variant("rs_missing"), _variant("rs_slow")], max_concurrent=2
    )

    assert written["rs_missing"].error == "model 'x' not found"
    assert written["rs_slow"].error == "Request timed out"
    assert attribution(written).written == 0


@pytest.mark.asyncio
async def test_a_variant_the_prompt_cannot_be_built_from_still_gets_a_card() -> None:
    """It used to raise straight past explain and cost the caller the row.

    The batch caught it and dropped one card; the CLI caught it and wrote
    nothing for that rsID at all, so the report simply had no line for a
    variant the analysis had found.
    """
    from allelio.ai import engine as engine_module

    engine = AIEngine()
    engine.available = True
    engine.client = StubClient()
    monkey = engine_module.build_variant_prompt
    engine_module.build_variant_prompt = _raise_on_prompt
    try:
        written = await engine.explain(_variant("rs1"))
    finally:
        engine_module.build_variant_prompt = monkey

    assert written.model is None
    assert "rs1" in written.text
    assert "no prompt for this one" in written.error


def _raise_on_prompt(result):
    raise ValueError("no prompt for this one")


def test_two_models_over_one_set_of_cards_are_both_named() -> None:
    """One run has one model, so this is the case nobody meets — until a server
    swaps the model out mid-run, or a saved payload is reopened. Naming one of
    the two would credit it for the other's pages, which is the whole defect
    this module exists to prevent."""
    credit = attribution(
        {
            "rs1": Explanation("Written.", "qwen3:8b"),
            "rs2": Explanation("Written.", "llama3.1:8b"),
            "rs3": Explanation("Written.", "llama3.1:8b"),
            "rs4": Explanation("Fallback.", None),
        }
    )

    # Sorted, so the sentence does not reshuffle between two readings of the
    # same payload.
    assert credit == ("llama3.1:8b, qwen3:8b", 3, 4)


def test_an_ollama_cloud_model_is_refused(monkeypatch) -> None:
    """The one case where 127.0.0.1:11434 is not this machine.

    Ollama forwards a `-cloud` tag to ollama.com, prompt and all, so every
    address check in the engine passes it — the name is the only place it shows.
    """
    monkeypatch.setenv("ALLELIO_MODEL", "gpt-oss:120b-cloud")

    with pytest.raises(ValueError, match="Ollama Cloud"):
        AIEngine()

    # And by argument, which is where the CLI's --model lands.
    with pytest.raises(ValueError, match="Ollama Cloud"):
        AIEngine(model="deepseek-v3.1:671b-cloud")

    # A local model with cloud in the middle of its name is not one of these.
    assert AIEngine(model="qwen-cloudy:7b").model == "qwen-cloudy:7b"


def test_the_report_escapes_what_came_out_of_the_uploaded_file() -> None:
    """rsID, category and chromosome are read off the user's own file.

    Self-inflicted, but the report is a file they open in a browser, and the
    rsID also lands inside an href.
    """
    from allelio.report import generate_html_report

    hostile = _variant('rs1"><script>alert(1)</script>')
    html = generate_html_report(
        [hostile], {}, "", {"model_used": "none", "generated_at": "now"}
    )

    assert "<script>alert(1)</script>" not in html
    assert "clinvar/?term=rs1%22%3E%3Cscript%3E" in html


def test_the_note_counts_answers_not_entries() -> None:
    """A failed call still fills a card, and that is not the model's work.

    Both reports below have one card with text on it. Which of them credits a
    model is decided by that card, and by nothing passed in beside it.
    """
    from allelio.report import generate_html_report

    metadata = {"generated_at": "now"}
    fallback = generate_html_report(
        [_variant()], {"rs429358": Explanation("Plain English.", None)}, "", metadata
    )
    assert "variants analyzed with" not in fallback
    assert "AI Model: none" in fallback

    written = generate_html_report(
        [_variant()], {"rs429358": Explanation("Plain English.", "llama3.1:8b")}, "", metadata
    )
    assert "1 of 1 variants analyzed with llama3.1:8b" in written


def test_the_whole_run_shares_one_event_loop(monkeypatch, tmp_path) -> None:
    """One asyncio.run() per variant closes the loop the client's pool is on.

    Measured against a real Ollama: call 1 ok, call 2 "Event loop is closed",
    call 3 ok — every second explanation silently became a fallback while the
    report still credited the model. Asserted on the loop the calls actually ran
    in, because a stub client has no pool to be bound to one.
    """
    from allelio.ai import engine as engine_module

    loops = []

    class Answering:
        async def list(self):
            loops.append(id(asyncio.get_running_loop()))
            return {"models": [{"model": "llama3.1:8b"}]}

        async def chat(self, **kwargs):
            loops.append(id(asyncio.get_running_loop()))
            return {"message": {"content": "A plain-English explanation."}}

    monkeypatch.setattr(engine_module, "AsyncClient", lambda **kwargs: Answering())
    result = _analyze(
        monkeypatch,
        tmp_path,
        variants=[_variant("rs1"), _variant("rs2"), _variant("rs3")],
    )

    assert "Generated 3 AI explanations" in " ".join(result.output.split())
    # Four now: the listing joined the same run, which is the point — asking for
    # it anywhere else would bind the client's pool to a loop that then closes.
    assert len(loops) == 4
    assert len(set(loops)) == 1


def test_the_headline_stat_counts_answers_too() -> None:
    """The note was fixed and the stat card above it was not.

    It is the largest number on the page, and it was crediting a model the
    footer on the same page said had written nothing.
    """
    from allelio.report import generate_html_report

    html = generate_html_report(
        [_variant()],
        {"rs429358": Explanation("Fallback text, not an explanation.", None)},
        "",
        {"generated_at": "now"},
    )

    stat = html.split('<div class="stat-value">')[-1].split("<")[0]
    assert stat == "0"
    assert "AI Explanations" in html


def test_the_downloaded_report_names_the_model(client: TestClient, monkeypatch) -> None:
    """The web export is the copy that leaves the browser and gets shown around.

    Read off the rows it prints, so the line and the rows underneath it cannot
    describe different runs.
    """
    from allelio.web import routes as routes_module

    named = "Qwen3.6-35B-A3B (OpenAI-compatible at http://127.0.0.1:1234/v1)"
    html = routes_module._generate_html_report(
        {
            "summary": "s",
            "results": [
                {"rsid": "rs1", "explanation": "Written.", "explained_by": named},
            ],
            "total_variants": 1,
            "analyzed_at": "now",
            "model_used": named,
        }
    )

    assert "AI Model:" in html
    assert f"{named} (1 of 1 explanations)" in html

    # And a run where nothing answered says so rather than naming a model.
    silent = routes_module._generate_html_report(
        {
            "summary": "s",
            "results": [{"rsid": "rs1", "explanation": "Fallback.", "explained_by": None}],
            "total_variants": 1,
            "analyzed_at": "now",
        }
    )
    assert "AI Model:</strong> none" in silent

    # A saved analysis from before the cards carried their credit has one name
    # for the whole run and says so; one from before even that says nothing was
    # written down, which is not the same as "no model".
    older = routes_module._generate_html_report(
        {"summary": "s", "results": [{"rsid": "rs1", "explanation": "x"}],
         "total_variants": 1, "analyzed_at": "now", "model_used": named}
    )
    assert f"{named} (whole run)" in older
    oldest = routes_module._generate_html_report(
        {"summary": "s", "results": [{"rsid": "rs1", "explanation": "x"}],
         "total_variants": 1, "analyzed_at": "now"}
    )
    assert "AI Model:</strong> not recorded" in oldest


def test_the_downloaded_report_counts_the_rows_it_prints() -> None:
    """The table stops at a hundred rows and the line above it did not.

    A genome with more significant variants than that read "150 of 150
    explanations" over a table holding a hundred, which is a count of a set the
    reader was never shown.
    """
    from allelio.web import routes as routes_module

    html = routes_module._generate_html_report(
        {
            "summary": "s",
            "results": [
                {"rsid": f"rs{i}", "explanation": "Written.", "explained_by": "llama3.1:8b"}
                for i in range(150)
            ],
            "total_variants": 150,
            "analyzed_at": "now",
        }
    )

    assert "llama3.1:8b (100 of 100 explanations)" in html
    assert html.count("<tr>") == 101  # the header row and the hundred it kept


def test_the_downloaded_report_escapes_the_model_name() -> None:
    from allelio.web import routes as routes_module

    html = routes_module._generate_html_report(
        {"summary": "s", "results": [], "total_variants": 0, "analyzed_at": "now",
         "model_used": '<img src=x onerror=alert(1)>'}
    )

    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_the_report_escapes_the_chromosome_off_the_uploaded_file() -> None:
    """The 23andMe parser checks the rsID prefix and the position, not this."""
    from allelio.report import generate_html_report

    hostile = _variant()
    hostile.chromosome = '19"><script>alert(1)</script>'
    html = generate_html_report(
        [hostile], {}, "", {"model_used": "none", "generated_at": "now"}
    )

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_a_port_of_zero_is_refused() -> None:
    """Dropping it would send the prompt to port 80 rather than fail."""
    from allelio.ai.engine import pin_to_loopback

    with pytest.raises(ValueError, match="port 0 is not a port"):
        pin_to_loopback("http://127.0.0.1:0/v1", "ALLELIO_OPENAI_BASE")


@pytest.mark.asyncio
async def test_a_cloud_model_is_refused_however_it_is_spelled(monkeypatch) -> None:
    """Ollama resolves model names case-insensitively; so must the refusal."""
    for spelling in ("gpt-oss:120b-CLOUD", "gpt-oss:120b-Cloud", "GPT-OSS:120B-CLOUD"):
        monkeypatch.setenv("ALLELIO_MODEL", spelling)
        with pytest.raises(ValueError, match="Ollama Cloud"):
            AIEngine()


@pytest.mark.asyncio
async def test_a_cloud_model_is_refused_when_the_server_names_it(monkeypatch) -> None:
    """__init__ never sees an adopted name.

    A signed-in Ollama user with one cloud model pulled serves exactly one, which
    is precisely the case the adoption path was written for.
    """
    _openai_server(monkeypatch, served=["gpt-oss:120b-cloud"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:11434/v1")

    engine = AIEngine()

    # The refusal cannot abort construction here — the server had not been asked
    # yet — so it stops the connection, and the model is never adopted.
    assert await engine.check_connection() is False
    assert engine.model == "llama3.1:8b"
    # And it says why. "No answer" would send them restarting a daemon that
    # answered perfectly well.
    assert "Ollama Cloud" in engine.refusal


def test_the_upload_does_not_name_a_model_that_never_answered(monkeypatch) -> None:
    """The web path has its own copy of the attribution rule.

    Nothing is listening in this test, so every card is the variant's own data
    wrapped in a disclaimer — which is exactly the text a reader would take for
    an explanation if the payload put a model's name on it.
    """
    from allelio.ai import engine as engine_module

    class Silent:
        async def list(self):
            raise ConnectionRefusedError("nothing there")

        async def chat(self, **kwargs):
            raise ConnectionRefusedError("nothing there")

    monkeypatch.setattr(engine_module, "AsyncClient", lambda **kwargs: Silent())

    from allelio.web import routes as routes_module

    class FakeDB:
        def is_initialized(self):
            return True

        def close(self):
            pass

    # Otherwise this needs the built 905 MB database and passes only on a
    # machine that has already run `allelio setup-db`.
    monkeypatch.setattr(routes_module, "AllelioDB", lambda *a, **k: FakeDB())
    monkeypatch.setattr(routes_module, "parse_genotype_file", lambda path: [_variant()])
    monkeypatch.setattr(
        routes_module, "analyze_variants", lambda genotypes, db: [_variant()]
    )

    response = TestClient(app, base_url="http://127.0.0.1").post(
        "/api/analyze",
        files={"file": ("genome.txt", b"rs429358\t19\t44908684\tCT\n", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["model_used"] == "none"


def test_the_suite_does_not_inherit_an_ollama_key() -> None:
    """A developer signed in to Ollama Cloud must get the same answers as CI.

    The fixture that clears it is the only thing standing between the two, and
    nothing else would notice if it stopped.
    """
    assert "OLLAMA_API_KEY" not in os.environ
    assert "OLLAMA_HOST" not in os.environ
    assert "ALLELIO_OPENAI_BASE" not in os.environ
    assert "ALLELIO_MODEL" not in os.environ


@pytest.mark.asyncio
async def test_a_name_the_server_made_up_is_not_adopted(monkeypatch) -> None:
    """An adopted name is printed on the page and written into the report.

    Whatever a server answers with ends up in front of the reader, so only
    something shaped like a model name is taken. The connection still stands —
    there is nothing wrong with the server, only with what it called itself.
    """
    _openai_server(monkeypatch, served=["<script>alert(1)</script>"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")

    engine = AIEngine()

    assert await engine.check_connection() is True
    assert engine.model == "llama3.1:8b"


def test_info_says_a_model_was_refused_rather_than_unreachable(monkeypatch) -> None:
    """The two are fixed by opposite actions, so they cannot share a message."""
    _openai_server(monkeypatch, served=["gpt-oss:120b-cloud"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:11434/v1")

    printed = _cli_info(monkeypatch)

    assert "Ollama Cloud" in printed
    assert "No answer from" not in printed


def test_analyze_stops_rather_than_relay_the_genome(monkeypatch, tmp_path) -> None:
    """A server whose only model is a cloud tag is a relay, and it is refused.

    This is the one abort left in `analyze`, and it happens before the genotype
    file is read: the refusal is only discoverable on the OpenAI-compatible
    path, where a single served model gets adopted, and asking costs one request
    to loopback.
    """
    seen = _openai_server(monkeypatch, served=["gpt-oss:120b-cloud"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:11434/v1")

    result = _analyze(monkeypatch, tmp_path)

    assert result.exit_code != 0
    assert "Ollama Cloud" in " ".join(result.output.split())
    assert not (tmp_path / "r.html").exists()
    # The name of this test is the assertion: the relay was asked what it
    # serves, and nothing else.
    assert [r.url.path for r in seen] == ["/v1/models"]


def test_the_upload_refuses_a_server_that_only_serves_a_cloud_model(
    monkeypatch, tmp_path
) -> None:
    """Same refusal as a remote address, and the same 400 with the reason."""
    _openai_server(monkeypatch, served=["gpt-oss:120b-cloud"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:11434/v1")

    raw = tmp_path / "genome.txt"
    raw.write_text("# rsid\tchromosome\tposition\tgenotype\nrs429358\t19\t44908684\tCT\n")

    with TestClient(app, base_url="http://127.0.0.1") as client:
        with open(raw, "rb") as fh:
            response = client.post("/api/analyze", files={"file": ("genome.txt", fh)})

    assert response.status_code == 400
    assert "Ollama Cloud" in response.json()["detail"]


@pytest.mark.asyncio
async def test_the_status_endpoint_carries_the_reason(monkeypatch) -> None:
    """The page has one line for this, and it should hold the actionable half."""
    _openai_server(monkeypatch, served=["gpt-oss:120b-cloud"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:11434/v1")

    with TestClient(app, base_url="http://127.0.0.1") as client:
        ai = client.get("/api/status").json()["ai"]

    assert ai["available"] is False
    assert "Ollama Cloud" in ai["error"]


# --- Round 5 findings -------------------------------------------------------


def _llama_swap(monkeypatch, models):
    """A stub llama-swap: canonical ids, each with the aliases it also routes on.

    Shape copied from the real server on 127.0.0.1:1234, which answers
    /v1/models with meta.llamaswap.aliases beside every id.
    """
    import httpx as real

    from allelio.ai import engine as engine_module

    def handler(request: "real.Request") -> "real.Response":
        if request.url.path.endswith("/models"):
            return real.Response(200, json={"data": [
                {
                    "id": name,
                    "object": "model",
                    "meta": {"llamaswap": {"aliases": list(aliases), "type": "model"}},
                }
                for name, aliases in models.items()
            ]})
        if request.url.path.endswith("/chat/completions"):
            return real.Response(
                200, json={"choices": [{"message": {"content": "Plain English."}}]}
            )
        return real.Response(404)

    monkeypatch.setattr(engine_module, "httpx", FakeHttpx(handler))


@pytest.mark.asyncio
async def test_an_alias_is_the_model(monkeypatch) -> None:
    """llama-swap routes on the aliases in its config, and they are not ids.

    `ALLELIO_MODEL=qwen36` is a working setup against the real server; called
    not-serving, it turns the status dot grey, makes `info` recommend a menu the
    name is already on, and makes generate_explanation refuse outright.
    """
    _llama_swap(monkeypatch, {"Qwen3.6-35B-A3B": ["qwen36"]})
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("ALLELIO_MODEL", "qwen36")

    engine = AIEngine()
    assert await engine.check_connection() is True
    assert engine.check_model_available() is True
    # Shown as the server spells it, though: an alias is for matching.
    assert engine.served_models == ["Qwen3.6-35B-A3B"]


@pytest.mark.asyncio
async def test_an_alias_does_not_make_a_server_look_like_it_serves_several(
    monkeypatch,
) -> None:
    """One model with two aliases is still one model, and still adoptable."""
    _llama_swap(monkeypatch, {"Qwen3.6-35B-A3B": ["qwen36", "qwen"]})
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")

    engine = AIEngine()
    assert await engine.check_connection() is True
    assert engine.model == "Qwen3.6-35B-A3B"


def test_analyze_skips_the_explanations_when_the_listing_says_the_model_is_not_there(
    monkeypatch, tmp_path
) -> None:
    """The contradiction is already in hand before the first prompt goes out.

    A server that answers a completion for a model it does not serve — and not
    all of them check — hands back another model's text, which then goes into
    the report under the name that was asked for. So no prompt is sent.

    The analysis needed no model at all, though. Refusing to write the report
    because an optional feature is misconfigured is the CLI disagreeing with its
    own web path, which degrades and returns the findings.
    """
    seen = _openai_server(monkeypatch, served=["qwen2.5-14b-instruct"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("ALLELIO_MODEL", "llama3.1:8b")

    result = _analyze(monkeypatch, tmp_path)

    assert result.exit_code == 0
    printed = " ".join(result.output.split())
    assert "is not serving" in printed
    assert "qwen2.5-14b-instruct" in printed
    # The report is written, and it credits nobody.
    report = (tmp_path / "r.html").read_text()
    assert "AI Model: none" in report
    assert "llama3.1:8b" not in report
    # Nothing was asked of the server past the listing.
    assert [r.url.path for r in seen] == ["/v1/models"]


def test_the_upload_does_not_credit_a_model_the_listing_does_not_have(
    monkeypatch, tmp_path
) -> None:
    """Same contradiction, the other path. The analysis is still worth having;
    the attribution on it is not."""
    from allelio.web import routes as routes_module

    _openai_server(monkeypatch, served=["qwen2.5-14b-instruct"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("ALLELIO_MODEL", "llama3.1:8b")

    class FakeDB:
        def is_initialized(self):
            return True

        def close(self):
            pass

    monkeypatch.setattr(routes_module, "AllelioDB", lambda *a, **k: FakeDB())
    monkeypatch.setattr(routes_module, "parse_genotype_file", lambda path: [_variant()])
    monkeypatch.setattr(routes_module, "analyze_variants", lambda *a, **k: [_variant()])

    raw = tmp_path / "genome.txt"
    raw.write_text("# rsid\tchromosome\tposition\tgenotype\nrs429358\t19\t44908684\tCT\n")

    with TestClient(app, base_url="http://127.0.0.1") as client:
        with open(raw, "rb") as fh:
            payload = client.post(
                "/api/analyze", files={"file": ("genome.txt", fh)}
            ).json()

    assert payload["model_used"] == "none"
    assert "llama3.1:8b" not in str(payload)


def test_a_refused_address_arrives_before_the_genome_is_read(
    monkeypatch, tmp_path
) -> None:
    """The README promises this happens before any analysis starts.

    Parsing a 16 MB file and matching 630,774 variants against ClinVar takes
    minutes; discovering the refusal afterwards is discovering it at the end.
    """
    import allelio.cli as cli_module

    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://104.18.7.1/v1")

    ran = []

    class FakeDB:
        def is_initialized(self):
            return True

        def version(self):
            return "test"

        def close(self):
            pass

    def parsed(path):
        ran.append("parse")
        return [_variant()]

    def analyzed(v, **kwargs):
        ran.append("analyze")
        return [_variant()]

    monkeypatch.setattr(cli_module, "AllelioDB", lambda *a, **k: FakeDB())
    monkeypatch.setattr(cli_module, "parse_genotype_file", parsed)
    monkeypatch.setattr(cli_module, "analyze_variants", analyzed)

    from click.testing import CliRunner

    raw = tmp_path / "genome.txt"
    raw.write_text("# rsid\tchromosome\tposition\tgenotype\nrs429358\t19\t44908684\tCT\n")
    result = CliRunner().invoke(
        cli_module.allelio,
        ["analyze", str(raw), "--output", str(tmp_path / "r.html")],
    )

    assert result.exit_code != 0
    assert ran == []


@pytest.mark.asyncio
async def test_the_batch_counts_only_answers_it_read() -> None:
    """A task can finish after the clock runs out and never be read.

    Counting those credits the model for pages nobody was given, and the
    per-task failure branch inflates `done`, so clamping to it is not enough.
    """
    engine = AIEngine()
    engine.available = True

    async def one_of_each(result):
        if result.rsid == "rs_slow":
            await asyncio.sleep(30)
            return Explanation("late", NAMED)
        if result.rsid == "rs_failed":
            return Explanation("fallback text", None)
        return Explanation("written by the model", NAMED)

    engine.explain = one_of_each

    explanations = await engine.explain_variants_batch(
        [VariantResult(rsid="rs_ok"), VariantResult(rsid="rs_failed"),
         VariantResult(rsid="rs_slow")],
        deadline=0.5,
    )

    assert explanations["rs_ok"].text == "written by the model"
    assert explanations["rs_ok"].model == NAMED
    # The one that came back late is on the page as its own data, uncredited —
    # the seed, not the answer nobody read.
    assert explanations["rs_slow"].model is None
    assert explanations["rs_failed"].model is None
    assert attribution(explanations).written == 1


@pytest.mark.asyncio
async def test_a_variant_that_fails_outside_the_guard_costs_one_variant() -> None:
    """It used to cost the whole upload, minutes after the analysis was done."""
    engine = AIEngine()
    engine.available = True

    async def boom(result):
        if result.rsid == "rs_bad":
            raise RuntimeError("something the guard never saw")
        return Explanation("fine", NAMED)

    engine.explain = boom

    explanations = await engine.explain_variants_batch(
        [VariantResult(rsid="rs_ok"), VariantResult(rsid="rs_bad")]
    )

    assert explanations["rs_ok"].text == "fine"
    # Seeded with its own data rather than dropped, and not credited to the
    # model that never saw it.
    assert "rs_bad" in explanations["rs_bad"].text
    assert explanations["rs_bad"].model is None
    assert attribution(explanations).written == 1


@pytest.mark.asyncio
async def test_the_listing_reads_the_objects_the_real_ollama_returns() -> None:
    """Every stub in this file answers with dicts; the library does not.

    ollama-python returns a ListResponse of Model objects, so the attribute
    branch of _model_names is the one every Ollama user takes. If it broke,
    `info` would tell all of them their model is missing and the suite would
    stay green.
    """
    from allelio.ai.engine import _model_names

    class Model:
        def __init__(self, name):
            self.model = name

    class ListResponse:
        models = [Model("llama3.1:8b"), Model("qwen2.5:14b")]

    assert _model_names(ListResponse()) == ["llama3.1:8b", "qwen2.5:14b"]


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:99999/v1",
    "http://127.0.0.1:abc/v1",
])
def test_a_port_that_is_not_a_port_is_refused(url) -> None:
    """urlsplit raises on both of these, and an unread exception here would
    escape as a traceback rather than the sentence explaining the setting."""
    from allelio.ai.engine import pin_to_loopback

    with pytest.raises(ValueError, match="ALLELIO_OPENAI_BASE"):
        pin_to_loopback(url, "ALLELIO_OPENAI_BASE")


@pytest.mark.asyncio
async def test_an_absurdly_long_name_is_not_adopted(monkeypatch) -> None:
    """The name goes on the page and into the report; there is a limit to it."""
    _openai_server(monkeypatch, served=["m" * 200])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")

    engine = AIEngine()

    assert await engine.check_connection() is True
    assert engine.model == "llama3.1:8b"


@pytest.mark.asyncio
async def test_a_refusal_does_not_outlive_the_server_that_caused_it(
    monkeypatch,
) -> None:
    """Restart the server with a local model and the old reason has to go.

    It is printed by `info` and returned by /api/status, both of which can ask
    twice in one process.
    """
    _openai_server(monkeypatch, served=["gpt-oss:120b-cloud"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:11434/v1")

    engine = AIEngine()
    assert await engine.check_connection() is False
    assert engine.refusal

    _openai_server(monkeypatch, served=["llama3.1:8b"])
    assert await engine.check_connection() is True
    assert engine.refusal is None


def test_a_missing_ollama_package_is_not_a_server_that_is_down(monkeypatch) -> None:
    """engine.py swallows the ImportError so the rest of the tool still runs,
    which left `info` telling people to start a daemon they cannot install."""
    from allelio.ai import engine as engine_module

    monkeypatch.setattr(engine_module, "AsyncClient", None)

    printed = _cli_info(monkeypatch)

    assert "pip install ollama" in printed
    assert "No answer from" not in printed


def test_a_query_string_cannot_swallow_the_endpoint() -> None:
    """The base has "/models" glued to it, so anything after the path has to go."""
    from allelio.ai.engine import pin_to_loopback

    assert pin_to_loopback("http://127.0.0.1:1234/v1?a=b#c", "ALLELIO_OPENAI_BASE") == (
        "http://127.0.0.1:1234/v1"
    )


def _run_attribution_block(results):
    """Run the page's own attribution branch over a payload, under node.

    One branch, in isolation: the caller decides what set it describes. That the
    page hands it the cards it is actually showing is _run_the_card_render's
    job, and that either is reached at all is §9's browser gate. node is
    required rather than skipped: this repo has no CI, so a skip is a check that
    quietly stops existing.
    """
    template = (
        pathlib.Path(__file__).resolve().parents[1]
        / "allelio/web/templates/index.html"
    ).read_text()
    block = template.split("// attribution-block start")[1].split(
        "// attribution-block end"
    )[0]

    node = shutil.which("node")
    if node is None:
        if os.environ.get("ALLELIO_NO_JS"):
            pytest.skip("ALLELIO_NO_JS is set")
        pytest.fail("node is needed to run the page's attribution branch")

    script = (
        "const el = {style: {}, textContent: null};\n"
        "const document = {getElementById: () => el};\n"
        + block
        + "\nrenderAttribution(" + json.dumps(results) + ");\n"
        "console.log(JSON.stringify(el));\n"
    )
    done = subprocess.run(
        [node, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _run_the_card_render(results, category):
    """Run the page's own card render, filter and all, under node.

    Wider than _run_attribution_block on purpose: it proves the line above the
    cards is recomputed from the cards actually rendered. Nothing is
    reimplemented here — every fenced region is the page's own source.
    """
    template = (
        pathlib.Path(__file__).resolve().parents[1]
        / "allelio/web/templates/index.html"
    ).read_text()

    def fenced(name):
        return template.split(f"// {name} start")[1].split(f"// {name} end")[0]

    node = shutil.which("node")
    if node is None:
        if os.environ.get("ALLELIO_NO_JS"):
            pytest.skip("ALLELIO_NO_JS is set")
        pytest.fail("node is needed to run the page's card render")

    script = (
        "const modelUsed = {style: {}, textContent: null};\n"
        "const container = {innerHTML: '', appendChild: () => {}};\n"
        "const document = {getElementById: id =>"
        " id === 'modelUsed' ? modelUsed : container};\n"
        "const createResultCard = () => ({});\n"
        "const analysisResults = " + json.dumps({"results": results}) + ";\n"
        "let currentCategory = " + json.dumps(category) + ";\n"
        + fenced("attribution-block")
        + fenced("slugify")
        + fenced("render-cards")
        + "\nrenderResultCards();\n"
        "console.log(JSON.stringify(modelUsed));\n"
    )
    done = subprocess.run(
        [node, "--input-type=module", "-e", script], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_page_counts_the_cards_the_tab_is_showing():
    """A tab filters the cards; the line above them used to keep the whole
    run's count, so three carrier cards none of which a model wrote sat under
    "12 of 50 explanations written by llama3.1:8b"."""
    results = [
        _card(category="Health Conditions", explained_by="llama3.1:8b"),
        _card(category="Health Conditions", explained_by="llama3.1:8b"),
        _card(category="Carrier Status", explained_by=None),
    ]

    everything = _run_the_card_render(results, "all")
    assert everything["textContent"] == (
        "2 of 3 explanations written by llama3.1:8b. The rest come straight "
        "from ClinVar and the GWAS Catalog."
    )

    carriers = _run_the_card_render(results, "carrier_status")
    assert carriers["textContent"] == (
        "No model wrote the explanations below. They come straight from "
        "ClinVar and the GWAS Catalog."
    )

    conditions = _run_the_card_render(results, "health_conditions")
    assert conditions["textContent"] == "Explanations written by llama3.1:8b."


def test_the_page_claims_nothing_when_there_are_no_results_to_claim():
    """The container is emptied on this path, and the line above it was left
    describing the analysis before it."""
    assert _run_the_card_render(None, "all")["style"]["display"] == "none"


def _run_credit_line(result):
    """Run the page's per-card credit line over one card, under node.

    Same reach and same limits as _run_attribution_block.
    """
    template = (
        pathlib.Path(__file__).resolve().parents[1]
        / "allelio/web/templates/index.html"
    ).read_text()
    block = template.split("// credit-line start")[1].split("// credit-line end")[0]

    node = shutil.which("node")
    if node is None:
        if os.environ.get("ALLELIO_NO_JS"):
            pytest.skip("ALLELIO_NO_JS is set")
        pytest.fail("node is needed to run the page's credit line")

    script = (
        "const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');\n"
        + block
        + "\nconsole.log(JSON.stringify(creditLine("
        + json.dumps(result)
        + ")));\n"
    )
    done = subprocess.run(
        [node, "--input-type=module", "-e", script], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_a_card_says_which_model_wrote_it():
    assert _run_credit_line(_card(explained_by="llama3.1:8b")) == (
        '<div class="result-credit">Written by llama3.1:8b.</div>'
    )


def test_a_card_the_model_did_not_write_says_where_it_came_from():
    assert _run_credit_line(_card(explained_by=None)) == (
        '<div class="result-credit">No model wrote this. Data from ClinVar '
        "and the GWAS Catalog.</div>"
    )


def test_a_card_from_before_the_credit_existed_claims_nothing():
    """The wrong way round is the expensive one: telling a reader that a model's
    own prose came from ClinVar dresses an 8B guess as a curated record."""
    assert _run_credit_line(_card()) == ""


def test_a_card_with_no_explanation_carries_no_credit_line():
    assert _run_credit_line(_card(explanation=None, explained_by=None)) == ""


def test_the_card_credit_escapes_the_model_name():
    """The name comes off the server and lands in the page's innerHTML."""
    assert "<img" not in _run_credit_line(_card(explained_by="<img src=x>"))


def _card(explanation="Plain English.", **extra):
    return dict({"rsid": "rs1", "explanation": explanation}, **extra)


def test_the_page_says_who_wrote_the_cards_when_they_all_came_from_the_model():
    el = _run_attribution_block([_card(explained_by="llama3.1:8b"), _card(explained_by="llama3.1:8b")])

    assert el["textContent"] == "Explanations written by llama3.1:8b."
    assert el["style"]["display"] == "block"


def test_the_page_says_how_many_when_only_some_came_from_the_model():
    el = _run_attribution_block(
        [_card(explained_by="llama3.1:8b"), _card(explained_by=None), _card(explained_by=None)]
    )

    assert el["textContent"].startswith("1 of 3 explanations written by llama3.1:8b.")


def test_the_page_names_no_model_when_none_wrote_a_card():
    el = _run_attribution_block([_card(explained_by=None), _card(explained_by=None)])

    assert el["textContent"] == (
        "No model wrote the explanations below. They come straight from ClinVar "
        "and the GWAS Catalog."
    )


def test_the_page_stays_quiet_about_a_payload_saved_before_the_cards_carried_credit():
    el = _run_attribution_block([_card(), _card()])

    assert el["textContent"] is None
    assert el["style"]["display"] == "none"


def test_a_card_with_no_explanation_does_not_dilute_the_count():
    """Below the top 50 there is no explanation to credit or not credit."""
    el = _run_attribution_block(
        [_card(explained_by="llama3.1:8b"), _card(explanation=None, explained_by=None)]
    )

    assert el["textContent"] == "Explanations written by llama3.1:8b."


def test_the_page_names_the_model_that_wrote_the_cards() -> None:
    """The status pill is fetched once at page load and can be stale by the time
    a half-hour run finishes; the payload's own attribution is not.

    A grep, and only a grep: nothing here runs the script, so this catches the
    element and the read being deleted but not the branch being made
    unreachable. That the line actually renders is asserted in the browser run.
    """
    template = (
        pathlib.Path(__file__).resolve().parents[1]
        / "allelio/web/templates/index.html"
    ).read_text()

    assert 'id="modelUsed"' in template
    # Counted off the cards, and off nothing else: no read of model_used is
    # left on the page for a partial run to contradict.
    assert "r.explained_by" in template
    assert "analysisResults.model_used" not in template
    assert "of ${explained.length} explanations written by" in template
    assert "Explanations written by ${names.join(', ')}." in template
    # Three states, not two: a payload saved before this key existed hides the
    # line rather than claiming nothing wrote cards a model did write.
    assert "No model wrote the explanations below." in template
    assert "!cards.some(r => 'explained_by' in r)" in template
    # And each card says for itself who wrote it.
    assert "No model wrote this. Data from ClinVar and the GWAS Catalog." in template
    # And the pill switches on the one word the engine answers with.
    assert "ai.status === 'serving'" in template
    assert "ai.status === 'unlisted'" in template
    assert "ai.status === 'refuted'" in template


# --- What the server said about itself ---------------------------------------
#
# The listing used to be a veto: a name that was not in it aborted the run, and
# a listing that never came back was read as no server at all. Both were wrong
# in the same way — they treated "the server did not say" as "the server said
# no" — and the model server this feature is about, a bare llama.cpp, has no
# /v1/models endpoint to say anything with. These pin the five answers apart.


@pytest.mark.asyncio
async def test_the_status_is_one_word_and_covers_every_case(monkeypatch) -> None:
    """The truth table three call sites used to work out for themselves."""
    from allelio.ai.engine import SERVING, REFUTED, UNLISTED, UNREACHABLE, REFUSED

    async def status_for(**kw):
        _openai_server(monkeypatch, **kw)
        monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")
        engine = AIEngine()
        await engine.check_connection()
        return engine

    monkeypatch.setenv("ALLELIO_MODEL", "llama3.1:8b")
    assert (await status_for(served=["llama3.1:8b"])).status == SERVING
    # Case is not a difference: Ollama resolves names case-insensitively, and
    # comparing them exactly refused a name the server was serving.
    assert (await status_for(served=["LLAMA3.1:8B"])).status == SERVING
    assert (await status_for(served=["qwen2.5-14b-instruct"])).status == REFUTED
    # An empty listing is an answer — "I serve nothing" — not a silence. A
    # fresh Ollama with nothing pulled is the commonest misconfiguration there
    # is, and it has to keep its `ollama pull` line.
    assert (await status_for(served=[])).status == REFUTED
    # No /v1/models at all: a bare llama.cpp. It has said nothing about its
    # models, which is not the same as saying it has not got this one.
    assert (await status_for(lists=False)).status == UNLISTED

    monkeypatch.delenv("ALLELIO_MODEL")
    refused = await status_for(served=["gpt-oss:120b-cloud"])
    assert refused.status == REFUSED
    # A refused model is not a refuted one. The listing came back and `listed`
    # is True, so a predicate that only asked "did it list, and is my model in
    # it" said the model was missing when the thing to print is the relay.
    assert refused.model_refuted() is False

    class Dead:
        async def list(self):
            raise ConnectionRefusedError("nothing there")

    engine = AIEngine()
    engine.client = Dead()
    await engine.check_connection()
    assert engine.status == UNREACHABLE
    assert engine.model_refuted() is False
    assert engine.will_explain() is False


@pytest.mark.asyncio
async def test_a_listing_that_never_came_back_is_not_a_server_that_is_down(
    monkeypatch,
) -> None:
    """A slow listing used to cost the whole run its explanations.

    A warming Ollama daemon takes its time over /api/tags while answering chat
    perfectly well, and a dead port answers ConnectError in milliseconds — so a
    clock that ran out is evidence of something being there, not of nothing.
    """
    from allelio.ai import engine as engine_module

    class Slow:
        async def list(self):
            await asyncio.sleep(30)

        async def chat(self, **kwargs):
            return {"message": {"content": "A plain-English explanation."}}

    monkeypatch.setattr(engine_module, "AsyncClient", lambda **kwargs: Slow())
    engine = AIEngine()
    assert await engine.check_connection() is True
    assert engine.status == "unlisted"
    assert engine.will_explain() is True


def test_analyze_explains_through_a_server_that_will_not_list_its_models(
    monkeypatch, tmp_path
) -> None:
    """The flagship configuration: a bare llama.cpp with no /v1/models."""
    _openai_server(monkeypatch, lists=False, served=["anything"], answers_anything=True)
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("ALLELIO_MODEL", "Qwen3-8B-Q4_K_M.gguf")

    result = _analyze(monkeypatch, tmp_path)
    printed = " ".join(result.output.split())

    assert result.exit_code == 0
    assert "Generated 1 AI explanations" in printed
    assert "Qwen3-8B-Q4_K_M.gguf" in (tmp_path / "r.html").read_text()


def test_analyze_prints_the_servers_own_reason_when_the_chat_fails(
    monkeypatch, tmp_path
) -> None:
    """`model 'x' not found` is the whole diagnostic, and it is in the body.

    raise_for_status() throws the body away and reports the status line and a
    link to MDN, so the one sentence that says what to change never reached the
    person on the path this feature is about.
    """
    _openai_server(monkeypatch, lists=False, served=["something-else"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:8080/v1")

    result = _analyze(monkeypatch, tmp_path)
    printed = " ".join(result.output.split())

    assert result.exit_code == 0
    assert "No explanations generated" in printed
    assert "model 'llama3.1:8b' not found" in printed
    # And the per-variant line agrees: a fallback card is not a tick.
    assert "[1/1] rs429358 \u2717" in printed
    assert "[1/1] rs429358 \u2713" not in printed
    report = (tmp_path / "r.html").read_text()
    assert "AI Model: none" in report


def test_analyze_sends_nothing_when_nothing_is_answering(monkeypatch, tmp_path) -> None:
    """No listing, no prompt, and a report either way."""
    from allelio.ai import engine as engine_module

    asked = []

    class Silent:
        async def list(self):
            asked.append("list")
            raise ConnectionRefusedError("nothing there")

        async def chat(self, **kwargs):
            asked.append("chat")
            raise ConnectionRefusedError("nothing there")

    monkeypatch.setattr(engine_module, "AsyncClient", lambda **kwargs: Silent())

    result = _analyze(monkeypatch, tmp_path)
    printed = " ".join(result.output.split())

    assert result.exit_code == 0
    assert "No answer from Ollama" in printed
    assert asked == ["list"]
    assert "AI Model: none" in (tmp_path / "r.html").read_text()


def test_analyze_tells_an_ollama_user_with_nothing_pulled_to_pull(
    monkeypatch, tmp_path
) -> None:
    """A fresh install lists {"models": []}, which is an answer and a menu."""
    from allelio.ai import engine as engine_module

    class Empty:
        async def list(self):
            return {"models": []}

        async def chat(self, **kwargs):
            raise AssertionError("no prompt should be sent")

    monkeypatch.setattr(engine_module, "AsyncClient", lambda **kwargs: Empty())

    result = _analyze(monkeypatch, tmp_path)
    printed = " ".join(result.output.split())

    assert result.exit_code == 0
    assert "is not serving" in printed
    assert "ollama pull llama3.1:8b" in printed
    assert "AI Model: none" in (tmp_path / "r.html").read_text()


def test_analyze_runs_a_model_named_in_the_wrong_case(monkeypatch, tmp_path) -> None:
    """Ollama resolves names case-insensitively; this used to refuse them.

    Measured against the real daemon: POST /api/chat with "LLAMA3.1:8B" answers
    200 and echoes that spelling back.
    """
    from allelio.ai import engine as engine_module

    class Answering:
        async def list(self):
            return {"models": [{"model": "llama3.1:8b"}]}

        async def chat(self, **kwargs):
            return {"message": {"content": "A plain-English explanation."}}

    monkeypatch.setattr(engine_module, "AsyncClient", lambda **kwargs: Answering())
    monkeypatch.setenv("ALLELIO_MODEL", "LLAMA3.1:8B")

    result = _analyze(monkeypatch, tmp_path)

    assert "Generated 1 AI explanations" in " ".join(result.output.split())
    # Credited in the spelling that was configured, which is the only honest
    # string available: Ollama echoes back whatever it was sent.
    assert "LLAMA3.1:8B" in (tmp_path / "r.html").read_text()


def test_the_upload_names_a_model_the_listing_only_answers_to_by_alias(
    monkeypatch,
) -> None:
    """llama-swap routes on names that are nowhere in its list of ids.

    ALLELIO_MODEL=qwen36 is a working configuration whose name appears only
    under meta.llamaswap.aliases — measured against the real server on :1234 —
    and the listing gate used to refuse it.
    """
    from allelio.web import routes as routes_module

    _llama_swap(monkeypatch, {"Qwen3.6-35B-A3B": ["qwen36", "qwen"]})
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("ALLELIO_MODEL", "qwen36")

    class FakeDB:
        def is_initialized(self):
            return True

        def close(self):
            pass

    monkeypatch.setattr(routes_module, "AllelioDB", lambda *a, **k: FakeDB())
    monkeypatch.setattr(routes_module, "parse_genotype_file", lambda path: [_variant()])
    monkeypatch.setattr(routes_module, "analyze_variants", lambda *a, **k: [_variant()])

    payload = (
        TestClient(app, base_url="http://127.0.0.1")
        .post(
            "/api/analyze",
            files={"file": ("genome.txt", b"rs429358\t19\t44908684\tCT\n", "text/plain")},
        )
        .json()
    )

    assert payload["model_used"].startswith("qwen36 (OpenAI-compatible")


def test_the_upload_does_not_credit_the_summary_to_the_cards(monkeypatch) -> None:
    """The summary is a separate call and can be the only one that answers.

    Counting it would put "Explanations written by X" over fifty cards X never
    wrote, which is the sentence the page renders from this key.
    """
    from allelio.web import routes as routes_module

    class OnlyTheSummary:
        async def list(self):
            return {"models": [{"model": "llama3.1:8b"}]}

        async def chat(self, model, messages, **kwargs):
            # The batch asks one variant at a time; the summary asks for a
            # summary. Only the second one is answered here.
            if "Summar" not in messages[-1]["content"]:
                raise RuntimeError("model is busy")
            return {"message": {"content": "Two findings worth a second look."}}

    from allelio.ai import engine as engine_module

    monkeypatch.setattr(engine_module, "AsyncClient", lambda **kwargs: OnlyTheSummary())

    class FakeDB:
        def is_initialized(self):
            return True

        def close(self):
            pass

    monkeypatch.setattr(routes_module, "AllelioDB", lambda *a, **k: FakeDB())
    monkeypatch.setattr(routes_module, "parse_genotype_file", lambda path: [_variant()])
    monkeypatch.setattr(routes_module, "analyze_variants", lambda *a, **k: [_variant()])

    payload = (
        TestClient(app, base_url="http://127.0.0.1")
        .post(
            "/api/analyze",
            files={"file": ("genome.txt", b"rs429358\t19\t44908684\tCT\n", "text/plain")},
        )
        .json()
    )

    assert payload["model_used"] == "none"
    # And the summary the model did write is still shown.
    assert "second look" in payload["summary"]


def test_the_upload_credits_the_cards_one_by_one(monkeypatch) -> None:
    """The run that no single name can describe: some answered, some did not.

    Fifty variants, a model that starts failing at variant twelve, and one
    string on the payload saying who wrote "the explanations" — that string is
    wrong for thirty-eight cards whichever way it is written. The credit is on
    each card instead, and there is no longer a run-level string for the page
    to read.
    """
    from allelio.web import routes as routes_module

    class AnswersOnce:
        async def list(self):
            return {"models": [{"model": "llama3.1:8b"}]}

        async def chat(self, model, messages, **kwargs):
            asked = messages[-1]["content"]
            if "Summar" in asked:
                return {"message": {"content": "Two findings worth a second look."}}
            if "rs1" in asked:
                return {"message": {"content": "A plain-English explanation."}}
            raise RuntimeError("model is busy")

    from allelio.ai import engine as engine_module

    monkeypatch.setattr(engine_module, "AsyncClient", lambda **kwargs: AnswersOnce())

    class FakeDB:
        def is_initialized(self):
            return True

        def close(self):
            pass

    found = [_variant("rs1"), _variant("rs2"), _variant("rs3")]
    monkeypatch.setattr(routes_module, "AllelioDB", lambda *a, **k: FakeDB())
    monkeypatch.setattr(routes_module, "parse_genotype_file", lambda path: found)
    monkeypatch.setattr(routes_module, "analyze_variants", lambda *a, **k: found)

    payload = (
        TestClient(app, base_url="http://127.0.0.1")
        .post(
            "/api/analyze",
            files={"file": ("genome.txt", b"rs1\t19\t44908684\tCT\n", "text/plain")},
        )
        .json()
    )

    cards = {r["rsid"]: r for r in payload["results"]}
    assert cards["rs1"]["explained_by"].startswith("llama3.1:8b (Ollama at ")
    # The two the model never wrote carry no name, on a run where it wrote one.
    assert cards["rs2"]["explained_by"] is None
    assert cards["rs3"]["explained_by"] is None
    # Their text is still there — the variant's own data — which is exactly why
    # the card has to say who wrote it.
    assert cards["rs2"]["explanation"]
    # And the payload's own count agrees with the cards, because it is read
    # off them.
    written = [r for r in payload["results"] if r["explained_by"]]
    assert len(written) == 1
    assert payload["model_used"] == cards["rs1"]["explained_by"]


def test_the_report_credits_the_cards_one_by_one() -> None:
    """The same partial run, in the file people keep and show around."""
    from allelio.report import generate_html_report

    html = generate_html_report(
        [_variant("rs1"), _variant("rs2")],
        {
            "rs1": Explanation("A plain-English explanation.", "llama3.1:8b"),
            "rs2": Explanation("Explanation: model is busy", None),
        },
        "",
        {"generated_at": "now"},
    )

    assert "1 of 2 variants analyzed with llama3.1:8b" in html
    assert "AI Analysis — llama3.1:8b" in html
    assert "No model wrote this" in html
    # One heading each, and the fallback card does not get the model's.
    assert html.count("AI Analysis — llama3.1:8b") == 1
    assert html.count("No model wrote this") == 1


def test_the_cli_credits_the_cards_one_by_one(monkeypatch, tmp_path) -> None:
    """Same run again, on the console and in the report it writes.

    The tick, the tally and the report all read the same records, so a run that
    wrote one of two cards cannot print two ticks, or say two, or head both
    cards with the model's name.
    """
    from allelio.ai import engine as engine_module

    class AnswersOnce:
        async def list(self):
            return {"models": [{"model": "llama3.1:8b"}]}

        async def chat(self, model, messages, **kwargs):
            if "rs1" in messages[-1]["content"]:
                return {"message": {"content": "A plain-English explanation."}}
            raise RuntimeError("model is busy")

    monkeypatch.setattr(engine_module, "AsyncClient", lambda **kwargs: AnswersOnce())

    result = _analyze(
        monkeypatch, tmp_path, variants=[_variant("rs1"), _variant("rs2")]
    )
    printed = " ".join(result.output.split())

    assert "[1/2] rs1 \u2713" in printed
    assert "[2/2] rs2 \u2717" in printed
    assert "Generated 1 AI explanations" in printed

    report = (tmp_path / "r.html").read_text()
    assert "1 of 2 variants analyzed with llama3.1:8b" in report
    assert report.count("AI Analysis \u2014 llama3.1:8b") == 1
    assert report.count("No model wrote this") == 1


def test_info_and_analyze_agree_about_a_server_that_will_not_list(
    monkeypatch, tmp_path
) -> None:
    """They used to disagree: `info` said the model was missing, `analyze` ran."""
    _openai_server(monkeypatch, lists=False, served=["x"], answers_anything=True)
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:8080/v1")

    printed_info = _cli_info(monkeypatch)
    printed_analyze = " ".join(_analyze(monkeypatch, tmp_path).output.split())

    assert "is not on that server" not in printed_info
    assert "is not serving" not in printed_analyze
    assert "answering at" in printed_info


def test_the_status_payload_carries_the_word_the_page_switches_on(
    monkeypatch,
) -> None:
    """A server that answers without listing is connected, not disconnected."""
    _openai_server(monkeypatch, lists=False)
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:8080/v1")

    body = TestClient(app, base_url="http://127.0.0.1").get("/api/status").json()

    assert body["ai"]["status"] == "unlisted"
    assert body["ai"]["available"] is True
    assert body["ai"]["model_available"] is False


@pytest.mark.asyncio
async def test_a_served_entry_this_shape_does_not_read_as_a_dead_server(
    monkeypatch,
) -> None:
    """Another process's JSON, parsed without trusting its shape.

    A TypeError in here lands in check_connection's blanket except, where a
    server that answered is reported as not being there at all.
    """
    from allelio.ai.engine import _aliases_of

    assert _aliases_of({"meta": {"llamaswap": {"aliases": "qwen36"}}}) == []
    assert _aliases_of({"meta": {"llamaswap": {"aliases": 7}}}) == []
    assert _aliases_of({"meta": {"llamaswap": {"aliases": ["qwen36"]}}}) == ["qwen36"]

    import httpx as real

    from allelio.ai import engine as engine_module

    def handler(request):
        return real.Response(200, json={"data": None})

    monkeypatch.setattr(engine_module, "httpx", FakeHttpx(handler))
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:1234/v1")
    engine = AIEngine()
    assert await engine.check_connection() is True
    assert engine.served_models == []
    # It answered and listed nothing, so it is refuted, not unreachable.
    assert engine.status == "refuted"


@pytest.mark.asyncio
async def test_the_bridge_raises_rather_than_hand_back_a_fallback(monkeypatch) -> None:
    """"or raises if no model answers" is the documented contract.

    A failed call returns the variant's own data wrapped in a disclaimer, and
    handing that to a caller that was promised an exception is handing it text
    it will present as an explanation.
    """
    from allelio.ai.explanations import generate_explanation

    _openai_server(monkeypatch, lists=False, served=["something-else"])
    monkeypatch.setenv("ALLELIO_OPENAI_BASE", "http://127.0.0.1:8080/v1")

    with pytest.raises(RuntimeError, match="not found"):
        await generate_explanation(_variant())


def test_analyze_says_the_package_is_missing_rather_than_the_server(
    monkeypatch, tmp_path
) -> None:
    """Only `allelio info` said this. engine.py swallows the ImportError."""
    from allelio.ai import engine as engine_module

    monkeypatch.setattr(engine_module, "AsyncClient", None)

    printed = " ".join(_analyze(monkeypatch, tmp_path).output.split())

    assert "pip install ollama" in printed
    assert "No answer from" not in printed


@pytest.mark.asyncio
async def test_a_reason_does_not_outlive_the_call_that_gave_it(monkeypatch) -> None:
    """last_error is printed after the run, so a stale one is a wrong sentence.

    One variant failing and the next one answering used to leave the first
    one's message on the engine, where the end-of-run line reads it.
    """
    from allelio.ai import engine as engine_module

    replies = [RuntimeError("model 'x' not found"), {"message": {"content": "Plain."}}]

    class Flaky:
        async def list(self):
            return {"models": [{"model": "llama3.1:8b"}]}

        async def chat(self, **kwargs):
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply

    monkeypatch.setattr(engine_module, "AsyncClient", lambda **kwargs: Flaky())
    engine = AIEngine()
    await engine.check_connection()

    await engine.explain(_variant())
    assert "not found" in engine.last_error
    await engine.explain(_variant())
    assert engine.last_error is None
