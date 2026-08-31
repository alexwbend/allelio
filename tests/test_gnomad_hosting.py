"""Tests for gnomAD hosting: manifest resolution, checksum verification, and
the consumer-array trimming in the build script."""

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from allelio.database import downloader
from allelio.database.downloader import (
    DEFAULT_GNOMAD_MANIFEST,
    GNOMAD_MANIFEST_URL,
    download_gnomad_from_manifest,
    fetch_gnomad_manifest,
    sha256_file,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# Checksum
# --------------------------------------------------------------------------

class TestSha256File:
    def test_matches_hashlib(self, tmp_dir):
        p = Path(tmp_dir) / "f.bin"
        p.write_bytes(b"allelio gnomad extract")
        assert sha256_file(str(p)) == hashlib.sha256(b"allelio gnomad extract").hexdigest()

    def test_large_file_chunked(self, tmp_dir):
        p = Path(tmp_dir) / "big.bin"
        data = b"x" * (3 * 1024 * 1024 + 7)  # spans multiple 1 MB chunks
        p.write_bytes(data)
        assert sha256_file(str(p)) == hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# Manifest resolution (the mutable pointer)
# --------------------------------------------------------------------------

class TestFetchManifest:
    def test_default_when_httpx_missing(self, monkeypatch):
        monkeypatch.setattr(downloader, "httpx", None)
        manifest = fetch_gnomad_manifest()
        assert manifest == DEFAULT_GNOMAD_MANIFEST

    def test_parses_remote_manifest(self, monkeypatch):
        remote = {
            "schema": 1,
            "source": "gnomAD",
            "version": "v9.9",
            "file": "x.tsv.gz",
            "sha256": "abc",
            "urls": ["https://example.test/x.tsv.gz"],
        }

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return remote

        monkeypatch.setattr(downloader.httpx, "get", lambda *a, **k: _Resp())
        assert fetch_gnomad_manifest() == remote

    def test_falls_back_on_malformed_manifest(self, monkeypatch):
        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"no": "urls"}

        monkeypatch.setattr(downloader.httpx, "get", lambda *a, **k: _Resp())
        assert fetch_gnomad_manifest() == DEFAULT_GNOMAD_MANIFEST

    def test_falls_back_on_network_error(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("offline")

        monkeypatch.setattr(downloader.httpx, "get", _boom)
        assert fetch_gnomad_manifest() == DEFAULT_GNOMAD_MANIFEST


# --------------------------------------------------------------------------
# Download + verify
# --------------------------------------------------------------------------

def _fake_download_writing(content: bytes):
    """Return a download_file stand-in that writes `content` to dest."""
    def _dl(url, dest_path, progress_callback=None, log=None, max_retries=3):
        Path(dest_path).write_bytes(content)
    return _dl


class TestDownloadFromManifest:
    def test_no_checksum_downloads_and_skips_verification(self, tmp_dir, monkeypatch):
        monkeypatch.setattr(downloader, "download_file", _fake_download_writing(b"data"))
        dest = Path(tmp_dir) / "g.tsv.gz"
        manifest = {"urls": ["https://a.test/g"], "sha256": None}
        assert download_gnomad_from_manifest(manifest, str(dest)) is True
        assert dest.read_bytes() == b"data"

    def test_matching_checksum_accepts(self, tmp_dir, monkeypatch):
        content = b"good bytes"
        monkeypatch.setattr(downloader, "download_file", _fake_download_writing(content))
        dest = Path(tmp_dir) / "g.tsv.gz"
        manifest = {
            "urls": ["https://a.test/g"],
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        assert download_gnomad_from_manifest(manifest, str(dest)) is True

    def test_mismatched_checksum_rejects_and_deletes(self, tmp_dir, monkeypatch):
        monkeypatch.setattr(downloader, "download_file", _fake_download_writing(b"wrong"))
        dest = Path(tmp_dir) / "g.tsv.gz"
        manifest = {"urls": ["https://a.test/g"], "sha256": "deadbeef"}
        assert download_gnomad_from_manifest(manifest, str(dest)) is False
        assert not dest.exists()

    def test_falls_through_to_second_url(self, tmp_dir, monkeypatch):
        good = b"the real file"
        good_sha = hashlib.sha256(good).hexdigest()
        calls = []

        def _dl(url, dest_path, progress_callback=None, log=None, max_retries=3):
            calls.append(url)
            if url.endswith("bad"):
                raise RuntimeError("404")
            Path(dest_path).write_bytes(good)

        monkeypatch.setattr(downloader, "download_file", _dl)
        dest = Path(tmp_dir) / "g.tsv.gz"
        manifest = {
            "urls": ["https://a.test/bad", "https://b.test/good"],
            "sha256": good_sha,
        }
        assert download_gnomad_from_manifest(manifest, str(dest)) is True
        assert calls == ["https://a.test/bad", "https://b.test/good"]

    def test_all_urls_fail(self, tmp_dir, monkeypatch):
        def _dl(url, dest_path, progress_callback=None, log=None, max_retries=3):
            raise RuntimeError("nope")

        monkeypatch.setattr(downloader, "download_file", _dl)
        dest = Path(tmp_dir) / "g.tsv.gz"
        manifest = {"urls": ["https://a.test/x", "https://b.test/y"], "sha256": None}
        assert download_gnomad_from_manifest(manifest, str(dest)) is False


# --------------------------------------------------------------------------
# Version pin + committed manifest
# --------------------------------------------------------------------------

class TestManifestPinning:
    def test_default_manifest_pins_v4_1_1(self):
        assert DEFAULT_GNOMAD_MANIFEST["version"] == "v4.1.1"
        assert DEFAULT_GNOMAD_MANIFEST["source"] == "gnomAD"

    def test_manifest_url_is_repo_hosted(self):
        assert GNOMAD_MANIFEST_URL.endswith("data/gnomad_manifest.json")

    def test_committed_manifest_is_valid_and_agrees(self):
        path = REPO_ROOT / "data" / "gnomad_manifest.json"
        assert path.exists(), "data/gnomad_manifest.json must be committed"
        manifest = json.loads(path.read_text())
        # The committed file is what the raw URL serves; its core fields must
        # match the built-in fallback so the two never disagree at publish time.
        for key in ("source", "version", "file"):
            assert manifest[key] == DEFAULT_GNOMAD_MANIFEST[key]
        assert manifest["urls"], "manifest must list at least one URL"


# --------------------------------------------------------------------------
# Build script: consumer-array trimming
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def build_script():
    """Import scripts/build_gnomad_freq.py as a module."""
    script_path = REPO_ROOT / "scripts" / "build_gnomad_freq.py"
    spec = importlib.util.spec_from_file_location("build_gnomad_freq", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestLoadArraySites:
    def test_plain_rsid_list(self, tmp_dir, build_script):
        p = Path(tmp_dir) / "sites.txt"
        p.write_text("rs111\nrs222\n# a comment\n\nrs333\n")
        assert build_script.load_array_sites(str(p)) == {"rs111", "rs222", "rs333"}

    def test_reads_first_column_of_genotype_file(self, tmp_dir, build_script):
        p = Path(tmp_dir) / "23andme.txt"
        p.write_text(
            "# rsid\tchromosome\tposition\tgenotype\n"
            "rs111\t1\t100\tAA\n"
            "rs222\t1\t200\tGG\n"
        )
        assert build_script.load_array_sites(str(p)) == {"rs111", "rs222"}


class TestProcessVcfTrim:
    def _write_vcf(self, path):
        with gzip.open(path, "wt") as f:
            f.write("##fileformat=VCFv4.2\n")
            f.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")
            f.write("21\t100\trs111\tA\tG\t.\tPASS\tAF=0.25;AC=5;AN=20\n")
            f.write("21\t200\trs222\tC\tT\t.\tPASS\tAF=0.10;AC=2;AN=20\n")
            f.write("21\t300\trs_a;rs_b\tT\tC\t.\tPASS\tAF=0.05;AC=1;AN=20\n")
            f.write("21\t400\t.\tA\tT\t.\tPASS\tAF=0.90\n")

    def test_trims_to_array_and_keeps_matched_multi_rsid(self, tmp_dir, build_script):
        vcf = Path(tmp_dir) / "chr21.vcf.bgz"
        self._write_vcf(str(vcf))
        out = Path(tmp_dir) / "out.tsv.gz"
        array = {"rs111", "rs_b"}
        with gzip.open(str(out), "wt") as out_f:
            out_f.write("\t".join(build_script.OUTPUT_COLUMNS) + "\n")
            n = build_script.process_vcf(str(vcf), out_f, 0, array)
        assert n == 2  # rs111 and rs_b; rs222 excluded, rs_a not in set, no-rsID skipped
        rows = [
            line.split("\t")[0]
            for line in gzip.open(str(out), "rt").read().splitlines()[1:]
        ]
        assert rows == ["rs111", "rs_b"]

    def test_no_array_keeps_all_rsid_variants(self, tmp_dir, build_script):
        vcf = Path(tmp_dir) / "chr21.vcf.bgz"
        self._write_vcf(str(vcf))
        out = Path(tmp_dir) / "out.tsv.gz"
        with gzip.open(str(out), "wt") as out_f:
            out_f.write("\t".join(build_script.OUTPUT_COLUMNS) + "\n")
            n = build_script.process_vcf(str(vcf), out_f, 0, None)
        # rs111, rs222, and both rs_a + rs_b (multi-rsID expands); no-rsID skipped
        assert n == 4


class TestStreamingDecode:
    """The streaming path decodes gzip/bgzip chunks without touching disk."""

    def _vcf_bytes(self):
        text = (
            "##fileformat=VCFv4.2\n"
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
            "21\t100\trs111\tA\tG\t.\tPASS\tAF=0.25;AC=5;AN=20\n"
            "21\t200\trs222\tC\tT\t.\tPASS\tAF=0.10;AC=2;AN=20\n"
        )
        return gzip.compress(text.encode("utf-8"))

    def _chunked(self, data, size):
        for i in range(0, len(data), size):
            yield data[i:i + size]

    def test_iter_gzip_lines_reassembles_across_tiny_chunks(self, build_script):
        # Feed the gzip stream 7 bytes at a time — lines must still reassemble.
        lines = list(build_script.iter_gzip_lines(self._chunked(self._vcf_bytes(), 7)))
        assert any(line.startswith("21\t100\trs111") for line in lines)
        assert any(line.startswith("21\t200\trs222") for line in lines)

    def test_streaming_parse_matches_disk_parse(self, tmp_dir, build_script):
        out = Path(tmp_dir) / "out.tsv.gz"
        with gzip.open(str(out), "wt") as out_f:
            out_f.write("\t".join(build_script.OUTPUT_COLUMNS) + "\n")
            lines = build_script.iter_gzip_lines(self._chunked(self._vcf_bytes(), 8))
            n = build_script.emit_records(lines, out_f, 0, {"rs111"})
        assert n == 1  # trimmed to rs111
        rows = gzip.open(str(out), "rt").read().splitlines()
        assert rows[-1].split("\t")[0] == "rs111"
