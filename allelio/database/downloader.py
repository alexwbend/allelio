"""Download and parse reference databases."""

import hashlib
import json
import re
import os
import zipfile
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime
from email.utils import parsedate_to_datetime

try:
    import httpx
except ImportError:
    httpx = None

from .store import AllelioDB
from .clinvar import parse_clinvar
from .gwas import parse_gwas
from .gnomad import parse_gnomad
from .clingen import parse_clingen, clingen_release_date
from .clinpgx import parse_clinpgx, clinpgx_release_date, extract_bundle


CLINVAR_URL = "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz"

# gnomAD allele frequency data — a compact TSV of consumer-array rsIDs plus
# allele frequencies, built from gnomAD v4.1.1 (CC0) with
# scripts/build_gnomad_freq.py (a few MB gzipped).
#
# Resolution goes through a JSON manifest rather than a hardcoded URL so that a
# version bump (gnomAD v5, a rebuild, a re-host) is a data refresh, not a code
# change. The manifest names the current file's source, version, sha256
# checksum, and one-or-more download URLs (permaweb primary, GitHub mirror).
# The permaweb copy (Arweave via Permavault) is content-addressed and never
# 404s — the exact failure that left this feature inert in v0.2.1.
GNOMAD_MANIFEST_URL = (
    "https://raw.githubusercontent.com/alexwbend/allelio/main/data/gnomad_manifest.json"
)

# Last-resort fallback used only if the manifest can't be fetched or parsed.
# Mirrors data/gnomad_manifest.json in the repo. `sha256` stays null until the
# extract is published; when null, the integrity check is skipped with a
# warning rather than blocking setup.
DEFAULT_GNOMAD_MANIFEST = {
    "schema": 1,
    "source": "gnomAD",
    "version": "v4.1.1",
    "file": "gnomad_v4.1.1_array_freq.tsv.gz",
    "sha256": "38b450846eddfa76a1e710f7e6dfdecb92763afe3430ae21778ee717a506ff5d",
    "urls": [
        # Permaweb (Arweave via Permavault) — content-addressed, never 404s.
        "https://arweave.net/sZmCL2kLlKvSTo_ob4p9by5q9HUBlBYBR2yEIsOsjos",
        # GitHub release mirror (fallback).
        "https://github.com/alexwbend/allelio/releases/download/"
        "v0.2.1-data/gnomad_v4.1.1_array_freq.tsv.gz",
    ],
}

# GWAS URL — the versioned FTP `releases/latest` path (verified 2026-08-31).
# EBI retired the GWAS Catalog API v1 in May 2026, so the old
# `www.ebi.ac.uk/gwas/api/search/downloads/associations/v1.0` endpoint is gone.
# This path is release-versioned and stable, and returns a zip containing the
# ontology-annotated associations TSV — extracted the same way as before.
GWAS_URL = "https://ftp.ebi.ac.uk/pub/databases/gwas/releases/latest/gwas-catalog-associations_ontology-annotated-full.zip"

# ClinGen gene-disease validity: which gene-disease links are established and
# how each is inherited. One CSV, ~1 MB, CC0 1.0 (ClinGen asks for attribution
# with the access date, which the report gives). Optional: setup continues
# without it, and inheritance then reads "not curated".
CLINGEN_URL = "https://search.clinicalgenome.org/kb/gene-validity/download"

# ClinPGx (formerly PharmGKB) clinical annotations: variant–drug evidence with
# per-genotype text. One zip, ~1.2 MB. License CC BY-SA 4.0 + no selling:
# fetched from ClinPGx at setup and never redistributed by Allelio (in
# particular, never placed on the permaweb). Optional and non-blocking.
CLINPGX_URL = "https://api.clinpgx.org/v1/download/file/data/clinicalAnnotations.zip"

# How old the local ClinVar/GWAS copy may get before `info`/`analyze` nudge the
# user to run `allelio update`. ClinVar refreshes weekly and GWAS periodically,
# so a few months is comfortably stale without being naggy.
STALENESS_THRESHOLD_DAYS = 90

BATCH_SIZE = 10000


def staleness_warning(db: AllelioDB, threshold_days: int = STALENESS_THRESHOLD_DAYS) -> Optional[str]:
    """Return a warning string if the local databases are older than the threshold.

    ClinVar and GWAS are rolling releases; a local copy that predates recent
    curation can miss or mis-rank variants. When the last update is older than
    ``threshold_days``, this returns a short message prompting `allelio update`.

    Args:
        db: AllelioDB instance to inspect.
        threshold_days: Age in days beyond which the data is considered stale.

    Returns:
        A warning message, or None if the data is fresh or its age is unknown.
    """
    # Advisory only — a freshness nudge must never break analysis, so any DB
    # that can't report its age (older schema, a test double) is treated as
    # "unknown" rather than raising.
    try:
        age_days = db.days_since_update()
    except Exception:
        return None
    if age_days is None or age_days < threshold_days:
        return None
    return (
        f"Local ClinVar/GWAS data is {int(age_days)} days old "
        f"(older than {threshold_days} days). "
        "Run `allelio update` to refresh to the latest release."
    )


def sources_summary(db: AllelioDB) -> Optional[str]:
    """One line naming each loaded source's release, or None if unknowable.

    Advisory, like ``staleness_warning``: a DB that cannot describe itself (an
    older schema, a test double) yields None rather than an exception, so the
    line is simply left out of the CLI, the report, and the status endpoint.
    """
    try:
        return db.describe_sources()
    except Exception:
        return None


def provenance_of(db: AllelioDB) -> dict:
    """Per-source provenance dict, or ``{}`` if the DB cannot provide one."""
    try:
        return dict(db.get_provenance())
    except Exception:
        return {}


def sha256_file(path: str) -> str:
    """Return the hex SHA-256 digest of a file, read in 1 MB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_http_date(value: Optional[str]) -> Optional[str]:
    """Turn an HTTP ``Last-Modified`` header into a ``YYYY-MM-DD`` string.

    Returns None when the header is missing or not an RFC 7231 date.
    """
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return None


def provenance_sidecar_path(path: str) -> Path:
    """Where ``download_file`` records what it fetched, beside the file."""
    return Path(str(path) + ".provenance.json")


def write_provenance(path: str, provenance: dict) -> None:
    """Persist a download's provenance beside the file (best effort)."""
    try:
        provenance_sidecar_path(path).write_text(json.dumps(provenance, indent=2))
    except OSError:
        pass


def read_provenance(path: str) -> dict:
    """Recover what is known about a reference file already on disk.

    Reads the sidecar written by ``download_file``. When there is none (a file
    downloaded before sidecars existed, or copied in by hand), falls back to the
    file's modification time and says so in ``release_source``, a reviewer
    should be able to tell a date the server asserted from one we inferred.

    Returns:
        Dict with keys ``url``, ``release`` (YYYY-MM-DD or None),
        ``release_source`` (``http-last-modified`` | ``file-mtime``),
        ``size`` and ``sha256`` (may be None if the file is missing).
    """
    path = Path(path)
    sidecar = provenance_sidecar_path(str(path))
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text())
            if isinstance(data, dict) and data.get("sha256"):
                return data
        except (OSError, ValueError):
            pass
    if not path.exists():
        return {"url": None, "release": None, "release_source": None, "size": None, "sha256": None}
    stat = path.stat()
    return {
        "url": None,
        "release": datetime.fromtimestamp(stat.st_mtime).date().isoformat(),
        "release_source": "file-mtime",
        "size": stat.st_size,
        "sha256": sha256_file(str(path)),
    }


# GWAS Catalog names the TSV inside its release zip with the release date, e.g.
# ``gwas_catalog_v1.0.2-associations_e114_r2026-09-04.tsv``. That ``r`` date is
# the catalogue's own release stamp, which beats the zip's Last-Modified.
_GWAS_RELEASE_RE = re.compile(r"_r(\d{4}-\d{2}-\d{2})")


def gwas_release_from_filename(name: Optional[str]) -> Optional[str]:
    """Extract the ``YYYY-MM-DD`` release date from a GWAS Catalog file name."""
    if not name:
        return None
    m = _GWAS_RELEASE_RE.search(name)
    return m.group(1) if m else None


def fetch_gnomad_manifest(
    url: str = GNOMAD_MANIFEST_URL, log: Optional[Callable] = None
) -> dict:
    """Fetch and parse the gnomAD data manifest.

    The manifest is the mutable pointer: editing it (new version, new checksum,
    new URLs) is how a data refresh happens without a code change. If it can't
    be fetched or is malformed, the built-in ``DEFAULT_GNOMAD_MANIFEST`` is
    returned so setup can still proceed.

    Args:
        url: Manifest URL (defaults to the repo-hosted manifest).
        log: Optional status logger.

    Returns:
        A manifest dict with at least ``urls``; always non-empty.
    """
    def _log(msg):
        if log:
            log(msg)

    if httpx is None:
        return dict(DEFAULT_GNOMAD_MANIFEST)

    try:
        resp = httpx.get(url, follow_redirects=True, timeout=30.0)
        resp.raise_for_status()
        manifest = resp.json()
        if not isinstance(manifest, dict) or not manifest.get("urls"):
            raise ValueError("manifest missing 'urls'")
        return manifest
    except Exception as e:
        _log(f"       Could not fetch gnomAD manifest ({e}); using built-in defaults.")
        return dict(DEFAULT_GNOMAD_MANIFEST)


def download_gnomad_from_manifest(
    manifest: dict,
    dest_path: str,
    progress_callback: Optional[Callable] = None,
    log: Optional[Callable] = None,
) -> bool:
    """Download the gnomAD extract named by a manifest, verifying its checksum.

    Tries each URL in the manifest in order until one downloads. If the
    manifest carries a ``sha256``, the downloaded file must match it or it is
    rejected and the next URL is tried. A manifest without a checksum downloads
    but skips verification (with a warning) rather than blocking.

    Args:
        manifest: Manifest dict (see ``fetch_gnomad_manifest``).
        dest_path: Where to save the downloaded file.
        progress_callback: Optional progress callback.
        log: Optional status logger.

    Returns:
        True if a file was downloaded (and verified, when a checksum was given).
    """
    def _log(msg):
        if log:
            log(msg)

    dest_path = Path(dest_path)
    urls = manifest.get("urls") or []
    expected = manifest.get("sha256")

    for url in urls:
        try:
            download_file(url, str(dest_path), progress_callback, log=log)
        except Exception as e:
            _log(f"       Source failed ({url}): {e}")
            continue

        if expected:
            actual = sha256_file(str(dest_path))
            if actual.lower() != str(expected).lower():
                _log(
                    f"       Checksum mismatch (expected {str(expected)[:12]}…, "
                    f"got {actual[:12]}…); rejecting this copy."
                )
                dest_path.unlink(missing_ok=True)
                continue
            _log("       Checksum verified.")
        else:
            _log("       No checksum in manifest — skipping integrity check.")

        return True

    return False


def download_file(url: str, dest_path: str, progress_callback: Optional[Callable] = None, log: Optional[Callable] = None, max_retries: int = 3) -> dict:
    """Download file from URL with progress reporting and retry logic.

    Args:
        url: URL to download from
        dest_path: Path to save file to
        progress_callback: Optional callback function(downloaded_bytes, total_bytes)
        log: Optional function to print status messages
        max_retries: Number of times to retry on failure

    Returns:
        Provenance dict (``url``, ``release`` from the server's Last-Modified
        header as YYYY-MM-DD, ``release_source``, ``size``, ``sha256``), also
        written to a ``.provenance.json`` sidecar beside the file so a later
        run that skips the download can still say what it has.

    Raises:
        ImportError: If httpx is not installed
        RuntimeError: If download fails after all retries
    """
    import time

    if httpx is None:
        raise ImportError("httpx is required for downloading. Install with: pip install httpx")

    def _log(msg):
        if log:
            log(msg)

    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, max_retries + 1):
        try:
            timeout = httpx.Timeout(30.0, read=300.0)
            with httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as response:
                response.raise_for_status()
                total_bytes = int(response.headers.get("content-length", 0))
                last_modified = _parse_http_date(response.headers.get("last-modified"))
                total_mb = total_bytes / (1024 * 1024) if total_bytes else 0

                downloaded = 0
                last_pct = -1
                with open(dest_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback:
                                progress_callback(downloaded, total_bytes)
                            # Print progress every 10%
                            if total_bytes > 0:
                                pct = int(downloaded * 100 / total_bytes) // 10 * 10
                                if pct > last_pct:
                                    last_pct = pct
                                    dl_mb = downloaded / (1024 * 1024)
                                    _log(f"       ... {dl_mb:.0f} MB / {total_mb:.0f} MB ({pct}%)")

            # Verify complete download
            actual_size = dest_path.stat().st_size
            if total_bytes > 0 and actual_size < total_bytes:
                raise RuntimeError(f"Incomplete download: got {actual_size:,} of {total_bytes:,} bytes")

            provenance = {
                "url": url,
                "release": last_modified,
                "release_source": "http-last-modified" if last_modified else None,
                "size": actual_size,
                "sha256": sha256_file(str(dest_path)),
                "downloaded_at": datetime.now().isoformat(timespec="seconds"),
            }
            write_provenance(str(dest_path), provenance)
            return provenance  # Success

        except Exception as e:
            if attempt < max_retries:
                wait = attempt * 10
                _log(f"       Download interrupted ({e}). Retrying in {wait}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                raise RuntimeError(f"Download failed after {max_retries} attempts: {e}")


def _record_source_provenance(db: AllelioDB, source: str, prov: dict) -> None:
    """Store one source's release date, URL, and checksum as DB metadata.

    Keys are ``<source>_release``, ``<source>_release_source``, ``<source>_url``,
    ``<source>_sha256`` and (GWAS only) ``<source>_release_file``. The legacy
    ``<source>_version`` key is kept pointing at the release date so older
    readers keep working.
    """
    prov = prov or {}
    release = prov.get("release") or "unknown"
    db.set_metadata(f"{source}_release", str(release))
    db.set_metadata(f"{source}_version", str(release))
    if prov.get("release_source"):
        db.set_metadata(f"{source}_release_source", str(prov["release_source"]))
    if prov.get("url"):
        db.set_metadata(f"{source}_url", str(prov["url"]))
    if prov.get("sha256"):
        db.set_metadata(f"{source}_sha256", str(prov["sha256"]))
    if prov.get("release_file"):
        db.set_metadata(f"{source}_release_file", str(prov["release_file"]))


def setup_database(
    db: AllelioDB,
    data_dir: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
    log: Optional[Callable] = None,
    include_gnomad: bool = True,
    force_download: bool = False,
    include_clingen: bool = True,
    include_clinpgx: bool = True,
) -> None:
    """Orchestrate full download, parse, and index of reference databases.

    Args:
        db: AllelioDB instance
        data_dir: Directory to store downloaded files. Defaults to ~/.allelio/data/
        progress_callback: Optional callback function for progress updates
        log: Optional function to print status messages (e.g. print or console.print)
        include_gnomad: If True, download gnomAD population frequency data (~1-2 GB)
        force_download: If True, re-fetch every source even when a copy is
            already on disk. ``allelio update`` sets this; without it an
            "update" only re-indexed whatever was already downloaded.

    Raises:
        ImportError: If httpx is not installed
        httpx.HTTPError: If download fails
    """
    def _log(msg):
        if log:
            log(msg)

    if data_dir is None:
        data_dir = os.path.expanduser("~/.allelio/data")

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    total_steps = (8 if include_gnomad else 6) + (2 if include_clingen else 0) + (2 if include_clinpgx else 0)

    # Initialize database tables
    _log(f"[1/{total_steps}] Creating database tables...")
    db.initialize()

    # Download ClinVar (skip if already downloaded and >100MB)
    clinvar_path = data_dir / "variant_summary.txt.gz"
    if not force_download and clinvar_path.exists() and clinvar_path.stat().st_size > 100_000_000:
        clinvar_mb = clinvar_path.stat().st_size / (1024 * 1024)
        _log(f"[2/{total_steps}] ClinVar already downloaded ({clinvar_mb:.0f} MB) — skipping download.")
        clinvar_prov = read_provenance(str(clinvar_path))
    else:
        _log(f"[2/{total_steps}] Downloading ClinVar from NIH (~400 MB)... this may take a few minutes")
        clinvar_prov = download_file(CLINVAR_URL, str(clinvar_path), progress_callback, log=log) or {}
        _log(f"[2/{total_steps}] ClinVar download complete.")
    clinvar_prov = clinvar_prov or {}
    clinvar_prov.setdefault("url", CLINVAR_URL)
    _log(f"       ClinVar release: {clinvar_prov.get('release') or 'unknown'}")

    # Parse ClinVar
    _log(f"[3/{total_steps}] Parsing ClinVar variants... (this takes 1-2 minutes)")
    # Start from empty so rows the new release no longer carries do not
    # survive beside the new ones.
    db.clear_table("clinvar")
    clinvar_count = 0
    clinvar_records = []
    for record in parse_clinvar(str(clinvar_path)):
        clinvar_records.append(record)
        clinvar_count += 1
        if len(clinvar_records) >= BATCH_SIZE:
            db.insert_clinvar_batch(clinvar_records)
            if clinvar_count % 500000 == 0:
                _log(f"       ... {clinvar_count:,} ClinVar records processed")
            clinvar_records = []

    if clinvar_records:
        db.insert_clinvar_batch(clinvar_records)
    _log(f"[3/{total_steps}] ClinVar complete: {clinvar_count:,} records loaded.")

    # Download GWAS (skip if already downloaded and >10MB, otherwise try multiple URLs)
    gwas_path = data_dir / "gwas_associations.tsv"
    gwas_zip_path = data_dir / "gwas_associations.zip"
    gwas_downloaded = False
    gwas_prov: dict = {}
    if not force_download and gwas_path.exists() and gwas_path.stat().st_size > 10_000_000:
        gwas_mb = gwas_path.stat().st_size / (1024 * 1024)
        _log(f"[4/{total_steps}] GWAS Catalog already downloaded ({gwas_mb:.0f} MB) — skipping download.")
        gwas_downloaded = True
        gwas_prov = read_provenance(str(gwas_path))
    else:
        _log(f"[4/{total_steps}] Downloading GWAS Catalog from EBI... this may take a few minutes")
        try:
            gwas_prov = dict(download_file(GWAS_URL, str(gwas_zip_path), progress_callback, log=log) or {})
            # The download is a zip file — extract the TSV from it
            _log("       Extracting zip file...")
            with zipfile.ZipFile(str(gwas_zip_path), 'r') as zf:
                # Find the TSV file inside the zip
                tsv_files = [f for f in zf.namelist() if f.endswith('.tsv')]
                if tsv_files:
                    # Extract the first TSV file and rename to our standard name
                    with zf.open(tsv_files[0]) as src, open(str(gwas_path), 'wb') as dst:
                        dst.write(src.read())
                    _log(f"       Extracted: {tsv_files[0]}")
                    gwas_prov["release_file"] = tsv_files[0]
                    # The catalogue stamps its own release date into the file
                    # name; prefer that over the zip's Last-Modified header.
                    stamped = gwas_release_from_filename(tsv_files[0])
                    if stamped:
                        gwas_prov["release"] = stamped
                        gwas_prov["release_source"] = "gwas-filename"
                else:
                    # No TSV found — maybe the zip contains the data directly
                    zf.extractall(str(data_dir))
                    _log(f"       Extracted {len(zf.namelist())} files")
            # Clean up zip
            gwas_zip_path.unlink(missing_ok=True)
            gwas_downloaded = True
            # The sidecar belongs beside the extracted TSV, which is the file a
            # later run finds on disk; the zip is gone by then.
            write_provenance(str(gwas_path), gwas_prov)
            _log(f"[4/{total_steps}] GWAS Catalog download complete.")
        except Exception as e:
            _log(f"       GWAS download failed: {e}")
            gwas_zip_path.unlink(missing_ok=True)
    if gwas_downloaded:
        gwas_prov = gwas_prov or {}
        gwas_prov.setdefault("url", GWAS_URL)
        _log(f"       GWAS Catalog release: {gwas_prov.get('release') or 'unknown'}")

    # Parse GWAS (if downloaded)
    gwas_count = 0
    if gwas_downloaded:
        _log(f"[5/{total_steps}] Parsing GWAS associations...")
        # Start from empty: GWAS rows are appended, not replaced, so a
        # re-index on top of the old rows doubled the table every time.
        db.clear_gwas()
        gwas_records = []
        for record in parse_gwas(str(gwas_path)):
            gwas_records.append(record)
            gwas_count += 1
            if len(gwas_records) >= BATCH_SIZE:
                db.insert_gwas_batch(gwas_records)
                if gwas_count % 100000 == 0:
                    _log(f"       ... {gwas_count:,} GWAS records processed")
                gwas_records = []

        if gwas_records:
            db.insert_gwas_batch(gwas_records)
        _log(f"[5/{total_steps}] GWAS complete: {gwas_count:,} records loaded.")
    else:
        _log(f"[4/{total_steps}] GWAS Catalog download failed from all sources.")
        _log(f"[5/{total_steps}] Skipping GWAS parsing — ClinVar data is still available.")
        _log("       You can retry later with: allelio update")

    # Download and parse gnomAD population frequencies (optional).
    # The file is a compact gzipped TSV of consumer-array rsIDs, built with
    # scripts/build_gnomad_freq.py. Its location, version, and checksum are
    # resolved from a JSON manifest so a data refresh needs no code change.
    gnomad_count = 0
    gnomad_downloaded = False
    gnomad_manifest = {}
    if include_gnomad:
        gnomad_path = data_dir / "gnomad_freq.tsv.gz"
        gnomad_manifest = fetch_gnomad_manifest(log=log)

        if not force_download and gnomad_path.exists() and gnomad_path.stat().st_size > 1_000_000:
            gnomad_mb = gnomad_path.stat().st_size / (1024 * 1024)
            _log(f"[6/{total_steps}] gnomAD already downloaded ({gnomad_mb:.0f} MB) — skipping download.")
            gnomad_downloaded = True
        else:
            gnomad_ver = gnomad_manifest.get("version", "")
            _log(
                f"[6/{total_steps}] Downloading gnomAD {gnomad_ver} population "
                "frequencies (compact array-site extract, a few MB)..."
            )
            try:
                gnomad_downloaded = download_gnomad_from_manifest(
                    gnomad_manifest, str(gnomad_path), progress_callback, log=log
                )
                if gnomad_downloaded:
                    _log(f"[6/{total_steps}] gnomAD download complete.")
                else:
                    _log("       gnomAD download failed from all sources in the manifest.")
                    _log("       Population frequency data will not be available.")
                    _log("       You can retry later with: allelio update")
            except Exception as e:
                _log(f"       gnomAD download failed: {e}")
                _log("       Population frequency data will not be available.")
                _log("       You can retry later with: allelio update")
                gnomad_path.unlink(missing_ok=True)

        if gnomad_downloaded:
            _log(f"[7/{total_steps}] Parsing gnomAD frequencies...")
            db.clear_table("gnomad")
            gnomad_records = []
            for record in parse_gnomad(str(gnomad_path)):
                gnomad_records.append(record)
                gnomad_count += 1
                if len(gnomad_records) >= BATCH_SIZE:
                    db.insert_gnomad_batch(gnomad_records)
                    if gnomad_count % 500000 == 0:
                        _log(f"       ... {gnomad_count:,} gnomAD records processed")
                    gnomad_records = []

            if gnomad_records:
                db.insert_gnomad_batch(gnomad_records)
            _log(f"[7/{total_steps}] gnomAD complete: {gnomad_count:,} variants with frequency data.")
        else:
            _log(f"[7/{total_steps}] Skipping gnomAD parsing — frequency data not available.")

    # ClinGen gene-disease validity (optional, small). Gives the mode of
    # inheritance the zygosity call needs to tell a carrier from an affected
    # genotype, and a validity classification per gene-disease pair.
    clingen_count = 0
    clingen_downloaded = False
    clingen_prov: dict = {}
    if include_clingen:
        step_dl = total_steps - (4 if include_clinpgx else 2)
        step_parse = step_dl + 1
        clingen_path = data_dir / "clingen_gene_validity.csv"
        if not force_download and clingen_path.exists() and clingen_path.stat().st_size > 100_000:
            _log(f"[{step_dl}/{total_steps}] ClinGen already downloaded, skipping download.")
            clingen_downloaded = True
            clingen_prov = read_provenance(str(clingen_path))
        else:
            _log(f"[{step_dl}/{total_steps}] Downloading ClinGen gene-disease validity (~1 MB)...")
            try:
                clingen_prov = dict(download_file(CLINGEN_URL, str(clingen_path), progress_callback, log=log) or {})
                clingen_downloaded = True
                _log(f"[{step_dl}/{total_steps}] ClinGen download complete.")
            except Exception as e:
                _log(f"       ClinGen download failed: {e}")
                _log("       Inheritance mode will read 'not curated'. Retry later with: allelio update")
                clingen_path.unlink(missing_ok=True)
        if clingen_downloaded:
            clingen_prov = clingen_prov or {}
            clingen_prov.setdefault("url", CLINGEN_URL)
            # The file stamps its own creation date; prefer that.
            try:
                stamped = clingen_release_date(str(clingen_path))
            except OSError:
                stamped = None
            if stamped:
                clingen_prov["release"] = stamped
                clingen_prov["release_source"] = "clingen-file-created"
                write_provenance(str(clingen_path), clingen_prov)
            _log(f"[{step_parse}/{total_steps}] Parsing ClinGen curations...")
            try:
                clingen_records = list(parse_clingen(str(clingen_path)))
                if not clingen_records:
                    raise ValueError("no curations found in the file")
                db.clear_table("clingen")
                db.insert_clingen_batch(clingen_records)
                clingen_count = len(clingen_records)
                _log(f"[{step_parse}/{total_steps}] ClinGen complete: {clingen_count:,} gene-disease curations "
                     f"(release {clingen_prov.get('release') or 'unknown'}).")
            except Exception as e:
                # Optional source: a bad file must not take setup down with it.
                _log(f"       ClinGen file could not be parsed ({e}); skipping.")
                clingen_downloaded = False
                clingen_path.unlink(missing_ok=True)
        else:
            _log(f"[{step_parse}/{total_steps}] Skipping ClinGen parsing, not available.")

    # ClinPGx clinical annotations (optional, small): variant–drug evidence
    # with the annotation text for each genotype. Only single-rsID
    # annotations are kept (see allelio/database/clinpgx.py).
    clinpgx_count = 0
    clinpgx_downloaded = False
    clinpgx_prov: dict = {}
    if include_clinpgx:
        step_dl, step_parse = total_steps - 2, total_steps - 1
        clinpgx_zip = data_dir / "clinpgx_clinical_annotations.zip"
        clinpgx_dir = data_dir / "clinpgx"
        if not force_download and clinpgx_zip.exists() and clinpgx_zip.stat().st_size > 100_000:
            _log(f"[{step_dl}/{total_steps}] ClinPGx already downloaded, skipping download.")
            clinpgx_downloaded = True
            clinpgx_prov = read_provenance(str(clinpgx_zip))
        else:
            _log(f"[{step_dl}/{total_steps}] Downloading ClinPGx clinical annotations (~1 MB)...")
            try:
                clinpgx_prov = dict(download_file(CLINPGX_URL, str(clinpgx_zip), progress_callback, log=log) or {})
                clinpgx_downloaded = True
                _log(f"[{step_dl}/{total_steps}] ClinPGx download complete.")
            except Exception as e:
                _log(f"       ClinPGx download failed: {e}")
                _log("       Pharmacogenomic annotations will not be available. Retry later with: allelio update")
                clinpgx_zip.unlink(missing_ok=True)
        if clinpgx_downloaded:
            clinpgx_prov = clinpgx_prov or {}
            clinpgx_prov.setdefault("url", CLINPGX_URL)
            _log(f"[{step_parse}/{total_steps}] Parsing ClinPGx annotations...")
            try:
                extract_bundle(str(clinpgx_zip), str(clinpgx_dir))
                stamped = clinpgx_release_date(str(clinpgx_dir))
                if stamped:
                    clinpgx_prov["release"] = stamped
                    clinpgx_prov["release_source"] = "clinpgx-created-marker"
                    write_provenance(str(clinpgx_zip), clinpgx_prov)
                records = list(parse_clinpgx(str(clinpgx_dir)))
                if not records:
                    raise ValueError("no single-rsID annotations found in the bundle")
                db.clear_table("clinpgx")
                db.insert_clinpgx_batch(records)
                clinpgx_count = len({r["annotation_id"] for r in records})
                _log(f"[{step_parse}/{total_steps}] ClinPGx complete: {clinpgx_count:,} single-rsID annotations, "
                     f"{len(records):,} genotype rows (release {clinpgx_prov.get('release') or 'unknown'}).")
            except Exception as e:
                _log(f"       ClinPGx bundle could not be parsed ({e}); skipping.")
                clinpgx_downloaded = False
                clinpgx_zip.unlink(missing_ok=True)
        else:
            _log(f"[{step_parse}/{total_steps}] Skipping ClinPGx parsing, not available.")

    # Set metadata
    _log(f"[{total_steps}/{total_steps}] Finalizing database...")
    db.set_metadata("last_update", datetime.now().isoformat())
    # Real provenance, not the word "latest": which release of each source this
    # database was built from, where it came from, and the checksum of the
    # exact file. A result is only reproducible if the reader can name the
    # ClinVar and GWAS releases behind it.
    _record_source_provenance(db, "clinvar", clinvar_prov)
    if gwas_downloaded:
        _record_source_provenance(db, "gwas", gwas_prov)
    else:
        db.set_metadata("gwas_version", "unavailable")
        db.set_metadata("gwas_release", "unavailable")
    # Provenance from the manifest, not hardcoded — so the frequency layer is
    # version-agnostic and a source/version change is a data refresh.
    if include_gnomad and gnomad_downloaded:
        db.set_metadata("gnomad_source", str(gnomad_manifest.get("source", "gnomAD")))
        db.set_metadata("gnomad_version", str(gnomad_manifest.get("version", "unknown")))
        gnomad_sha = gnomad_manifest.get("sha256")
        if not gnomad_sha:
            try:
                gnomad_sha = sha256_file(str(gnomad_path))
            except OSError:
                gnomad_sha = None
        if gnomad_sha:
            db.set_metadata("gnomad_sha256", str(gnomad_sha))
        if gnomad_manifest.get("urls"):
            db.set_metadata("gnomad_url", str(gnomad_manifest["urls"][0]))
    else:
        # Either skipped by flag or failed to download: say so, rather than
        # leaving the key absent and the release reading "unknown".
        db.set_metadata("gnomad_version", "unavailable")
        db.set_metadata("gnomad_release", "unavailable")

    if include_clingen and clingen_downloaded:
        _record_source_provenance(db, "clingen", clingen_prov)
    else:
        db.set_metadata("clingen_version", "unavailable")
        db.set_metadata("clingen_release", "unavailable")

    if include_clinpgx and clinpgx_downloaded:
        _record_source_provenance(db, "clinpgx", clinpgx_prov)
    else:
        db.set_metadata("clinpgx_version", "unavailable")
        db.set_metadata("clinpgx_release", "unavailable")

    parts = [f"{clinvar_count:,} ClinVar"]
    if gwas_count > 0:
        parts.append(f"{gwas_count:,} GWAS")
    if gnomad_count > 0:
        parts.append(f"{gnomad_count:,} gnomAD")
    if clingen_count > 0:
        parts.append(f"{clingen_count:,} ClinGen")
    if clinpgx_count > 0:
        parts.append(f"{clinpgx_count:,} ClinPGx")
    _log(f"Done! Database ready with {' + '.join(parts)} records.")
