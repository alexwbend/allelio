"""Tests for the web interface.

The web module went unexercised long enough to accumulate a startup crash, two
missing awaits and three wrong method names, so these cover the wiring: the
routes answer, CORS is not open to the world, and the AI engine's two entry
points survive a round trip against a stubbed client.
"""

import asyncio
import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from allelio.ai.engine import AIEngine
from allelio.analysis.lookup import ClinVarEntry, GWASEntry, VariantResult
from allelio.web.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1")


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
