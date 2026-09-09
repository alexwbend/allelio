"""Reference-data provenance: which release of each source a database holds.

A finding is only reproducible against the exact ClinVar and GWAS releases it
was computed from. These tests pin the plumbing that records the release date
and checksum at setup and surfaces them in the CLI, the HTML report, and the
web status endpoint.
"""

import gzip
import io
import json
import os
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from allelio.database import downloader
from allelio.database.store import AllelioDB
from allelio.report import generate_html_report


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestHttpDate:
    def test_parses_rfc7231(self):
        assert downloader._parse_http_date("Sun, 06 Sep 2026 14:42:05 GMT") == "2026-09-06"

    def test_none_when_missing_or_garbage(self):
        assert downloader._parse_http_date(None) is None
        assert downloader._parse_http_date("") is None
        assert downloader._parse_http_date("yesterday-ish") is None


class TestGwasFilenameRelease:
    def test_extracts_r_date(self):
        name = "gwas_catalog_v1.0.2-associations_e114_r2026-09-04.tsv"
        assert downloader.gwas_release_from_filename(name) == "2026-09-04"

    def test_none_for_unstamped_name(self):
        assert downloader.gwas_release_from_filename("gwas-catalog-download-associations-alt-full.tsv") is None
        assert downloader.gwas_release_from_filename(None) is None


class TestSidecar:
    def test_round_trip(self, tmp_dir):
        f = Path(tmp_dir) / "variant_summary.txt.gz"
        f.write_bytes(b"x")
        prov = {"url": "u", "release": "2026-09-06", "release_source": "http-last-modified", "size": 1, "sha256": "ab"}
        downloader.write_provenance(str(f), prov)
        assert downloader.provenance_sidecar_path(str(f)).exists()
        assert downloader.read_provenance(str(f)) == prov

    def test_falls_back_to_mtime_and_says_so(self, tmp_dir):
        f = Path(tmp_dir) / "variant_summary.txt.gz"
        f.write_bytes(b"hello")
        prov = downloader.read_provenance(str(f))
        assert prov["release_source"] == "file-mtime"
        assert prov["release"] == datetime.fromtimestamp(f.stat().st_mtime).date().isoformat()
        assert prov["sha256"] == downloader.sha256_file(str(f))
        assert prov["url"] is None

    def test_missing_file_is_all_unknown(self, tmp_dir):
        prov = downloader.read_provenance(str(Path(tmp_dir) / "nope"))
        assert prov["release"] is None and prov["sha256"] is None

    def test_malformed_sidecar_ignored(self, tmp_dir):
        f = Path(tmp_dir) / "f"
        f.write_bytes(b"data")
        downloader.provenance_sidecar_path(str(f)).write_text("{not json")
        assert downloader.read_provenance(str(f))["release_source"] == "file-mtime"


class _FakeResponse:
    """Minimal stand-in for httpx.stream()'s response."""

    def __init__(self, body: bytes, last_modified: str):
        self._body = body
        self.headers = {"content-length": str(len(body)), "last-modified": last_modified}

    def raise_for_status(self):
        pass

    def iter_bytes(self, chunk_size=65536):
        yield self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestDownloadFileProvenance:
    def test_returns_and_persists_provenance(self, tmp_dir, monkeypatch):
        body = b"reference-data"
        monkeypatch.setattr(
            downloader.httpx, "stream",
            lambda *a, **k: _FakeResponse(body, "Sun, 06 Sep 2026 14:42:05 GMT"),
        )
        dest = Path(tmp_dir) / "variant_summary.txt.gz"
        prov = downloader.download_file("https://example/x.gz", str(dest))
        assert dest.read_bytes() == body
        assert prov["release"] == "2026-09-06"
        assert prov["release_source"] == "http-last-modified"
        assert prov["sha256"] == downloader.sha256_file(str(dest))
        assert prov["size"] == len(body)
        assert prov["url"] == "https://example/x.gz"
        # A later run that skips the download recovers the same facts.
        assert downloader.read_provenance(str(dest))["release"] == "2026-09-06"


def _clinvar_gz(path: Path):
    header = "\t".join(f"c{i}" for i in range(34)).replace("c0", "#AlleleID")
    row = ["0"] * 34
    row[4] = "BRCA2"; row[6] = "Pathogenic"; row[9] = "80359550"; row[16] = "GRCh38"; row[24] = "criteria provided, single submitter"
    with gzip.open(path, "wt") as f:
        f.write(header + "\n" + "\t".join(row) + "\n")


def _gwas_zip_bytes() -> bytes:
    header = "\t".join(["SNPS", "SNP_ID_CURRENT", "DISEASE/TRAIT", "P-VALUE", "OR or BETA", "MAPPED_GENE", "STUDY", "PUBMEDID", "LINK"])
    row = "\t".join(["rs1", "1", "Height", "1e-9", "1.1", "G", "S", "1", "L"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("gwas-catalog-download-associations-alt-full.tsv", header + "\n" + row + "\n")
    return buf.getvalue()


class TestSetupRecordsProvenance:
    def _run(self, tmp_dir, monkeypatch, force=False):
        data_dir = Path(tmp_dir) / "data"
        data_dir.mkdir()
        clinvar_gz = data_dir / "prebuilt.gz"
        _clinvar_gz(clinvar_gz)
        clinvar_bytes = clinvar_gz.read_bytes()
        gwas_bytes = _gwas_zip_bytes()
        calls = []

        def fake_download(url, dest, progress_callback=None, log=None, max_retries=3):
            calls.append(url)
            body = clinvar_bytes if "clinvar" in url else gwas_bytes
            lm = "2026-09-06" if "clinvar" in url else "2026-09-04"
            Path(dest).write_bytes(body)
            prov = {"url": url, "release": lm, "release_source": "http-last-modified",
                    "size": len(body), "sha256": downloader.sha256_file(dest)}
            downloader.write_provenance(dest, prov)
            return prov

        monkeypatch.setattr(downloader, "download_file", fake_download)
        db = AllelioDB(str(Path(tmp_dir) / "a.db"))
        downloader.setup_database(db, data_dir=str(data_dir), include_gnomad=False, force_download=force)
        return db, calls, data_dir

    def test_release_dates_and_checksums_stored(self, tmp_dir, monkeypatch):
        db, calls, _ = self._run(tmp_dir, monkeypatch)
        assert db.get_metadata("clinvar_release") == "2026-09-06"
        assert db.get_metadata("gwas_release") == "2026-09-04"
        # The legacy key no longer says "latest".
        assert db.get_metadata("clinvar_version") == "2026-09-06"
        assert len(db.get_metadata("clinvar_sha256")) == 64
        assert len(db.get_metadata("gwas_sha256")) == 64
        assert db.get_metadata("clinvar_url") == downloader.CLINVAR_URL
        assert db.get_metadata("gwas_url") == downloader.GWAS_URL
        assert db.get_metadata("gwas_release_file") == "gwas-catalog-download-associations-alt-full.tsv"
        prov = db.get_provenance()
        assert prov["clinvar"]["release"] == "2026-09-06"
        assert prov["gwas"]["release_source"] == "http-last-modified"
        assert prov["gnomad"]["release"] == "unavailable"
        assert db.describe_sources() == "ClinVar 2026-09-06 · GWAS Catalog 2026-09-04"
        assert db.version().startswith("ClinVar 2026-09-06 · GWAS Catalog 2026-09-04 (built ")

    def test_gwas_sidecar_sits_beside_the_extracted_tsv(self, tmp_dir, monkeypatch):
        _, _, data_dir = self._run(tmp_dir, monkeypatch)
        sidecar = downloader.provenance_sidecar_path(str(data_dir / "gwas_associations.tsv"))
        assert sidecar.exists()
        assert json.loads(sidecar.read_text())["release"] == "2026-09-04"

    def test_existing_files_are_not_refetched_without_force(self, tmp_dir, monkeypatch):
        db, calls, data_dir = self._run(tmp_dir, monkeypatch)
        assert len(calls) == 2
        # Make the on-disk copies clear the "already downloaded" size gates.
        (data_dir / "variant_summary.txt.gz").write_bytes(b"0" * 100_000_001)
        (data_dir / "gwas_associations.tsv").write_bytes(b"0" * 10_000_001)
        monkeypatch.setattr(downloader, "download_file", lambda *a, **k: calls.append(a[0]))
        again = AllelioDB(str(Path(tmp_dir) / "b.db"))
        try:
            downloader.setup_database(again, data_dir=str(data_dir), include_gnomad=False)
        except Exception:
            pass  # the padded files are not parseable; only the fetch count matters
        assert len(calls) == 2

    def test_force_download_refetches_existing_files(self, tmp_dir, monkeypatch):
        db, calls, data_dir = self._run(tmp_dir, monkeypatch)
        (data_dir / "variant_summary.txt.gz").write_bytes(b"0" * 100_000_001)
        (data_dir / "gwas_associations.tsv").write_bytes(b"0" * 10_000_001)
        # Same data dir, force on: both sources fetched again and provenance refreshed.
        from allelio.database import downloader as dl
        fetched = []
        orig = dl.download_file
        def counting(url, dest, *a, **kw):
            fetched.append(url)
            return orig(url, dest, *a, **kw)
        monkeypatch.setattr(dl, "download_file", counting)
        again = AllelioDB(str(Path(tmp_dir) / "c.db"))
        dl.setup_database(again, data_dir=str(data_dir), include_gnomad=False, force_download=True)
        assert len(fetched) == 2
        assert again.get_metadata("clinvar_release") == "2026-09-06"


class TestReindexDoesNotDuplicateGwas:
    def test_second_setup_keeps_one_copy(self, tmp_dir, monkeypatch):
        runner = TestSetupRecordsProvenance()
        db, _, data_dir = runner._run(tmp_dir, monkeypatch)
        db.cursor.execute("SELECT COUNT(*) FROM gwas")
        first = db.cursor.fetchone()[0]
        assert first == 1
        # Same database, same on-disk files: an update must not append.
        downloader.setup_database(db, data_dir=str(data_dir), include_gnomad=False, force_download=True)
        db.cursor.execute("SELECT COUNT(*) FROM gwas")
        assert db.cursor.fetchone()[0] == first


    def test_reindex_drops_rows_the_release_no_longer_carries(self, tmp_dir, monkeypatch):
        runner = TestSetupRecordsProvenance()
        db, _, data_dir = runner._run(tmp_dir, monkeypatch)
        db.insert_clinvar_batch([{"rsid": "rs_withdrawn", "ref_allele": "A", "alt_allele": "G",
                                  "gene": "X", "clinical_significance": "Pathogenic",
                                  "conditions": "c", "review_status": "r", "last_evaluated": ""}])
        downloader.setup_database(db, data_dir=str(data_dir), include_gnomad=False, force_download=True)
        assert db.lookup_rsid("rs_withdrawn")["clinvar"] == []
        db.cursor.execute("SELECT COUNT(*) FROM clinvar")
        assert db.cursor.fetchone()[0] == 1


class TestLegacyDatabase:
    def test_latest_is_not_a_release(self, tmp_dir):
        db = AllelioDB(str(Path(tmp_dir) / "a.db"))
        db.initialize()
        db.set_metadata("clinvar_version", "latest")
        db.set_metadata("gwas_version", "latest")
        prov = db.get_provenance()
        assert prov["clinvar"]["release"] is None
        assert "ClinVar unknown" in db.describe_sources()

    def test_stats_carry_provenance(self, tmp_dir):
        db = AllelioDB(str(Path(tmp_dir) / "a.db"))
        db.initialize()
        db.set_metadata("clinvar_release", "2026-09-06")
        assert db.get_stats()["provenance"]["clinvar"]["release"] == "2026-09-06"


class TestReportShowsProvenance:
    def test_footer_names_releases_and_checksums(self):
        prov = {
            "clinvar": {"label": "ClinVar", "release": "2026-09-06", "release_source": "http-last-modified", "url": None, "sha256": "abcdef0123456789" + "0" * 48},
            "gwas": {"label": "GWAS Catalog", "release": "2026-09-04", "release_source": "file-mtime", "url": None, "sha256": None},
            "gnomad": {"label": "gnomAD", "release": "unavailable", "release_source": None, "url": None, "sha256": None},
        }
        html = generate_html_report(results=[], explanations={}, summary="s", metadata={"provenance": prov})
        assert "ClinVar: https://www.ncbi.nlm.nih.gov/clinvar &mdash; release 2026-09-06, sha256 abcdef012345…" in html
        assert "GWAS Catalog: https://www.ebi.ac.uk/gwas &mdash; release 2026-09-04 (from file date)" in html
        assert "gnomAD: https://gnomad.broadinstitute.org &mdash; not loaded" in html

    def test_unknown_when_not_recorded(self):
        html = generate_html_report(results=[], explanations={}, summary="s", metadata={})
        assert "release unknown" in html
