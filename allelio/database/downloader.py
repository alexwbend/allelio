"""Download and parse reference databases."""

import hashlib
import json
import os
import zipfile
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime

try:
    import httpx
except ImportError:
    httpx = None

from .store import AllelioDB
from .clinvar import parse_clinvar
from .gwas import parse_gwas
from .gnomad import parse_gnomad


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
    "sha256": None,
    "urls": [
        # Permaweb (Arweave via Permavault) — filled in once published.
        # "https://arweave.net/<tx-id>",
        # GitHub release mirror (fallback during transition).
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


def sha256_file(path: str) -> str:
    """Return the hex SHA-256 digest of a file, read in 1 MB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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


def download_file(url: str, dest_path: str, progress_callback: Optional[Callable] = None, log: Optional[Callable] = None, max_retries: int = 3) -> None:
    """Download file from URL with progress reporting and retry logic.

    Args:
        url: URL to download from
        dest_path: Path to save file to
        progress_callback: Optional callback function(downloaded_bytes, total_bytes)
        log: Optional function to print status messages
        max_retries: Number of times to retry on failure

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

            return  # Success

        except Exception as e:
            if attempt < max_retries:
                wait = attempt * 10
                _log(f"       Download interrupted ({e}). Retrying in {wait}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                raise RuntimeError(f"Download failed after {max_retries} attempts: {e}")


def setup_database(
    db: AllelioDB,
    data_dir: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
    log: Optional[Callable] = None,
    include_gnomad: bool = True,
) -> None:
    """Orchestrate full download, parse, and index of reference databases.

    Args:
        db: AllelioDB instance
        data_dir: Directory to store downloaded files. Defaults to ~/.allelio/data/
        progress_callback: Optional callback function for progress updates
        log: Optional function to print status messages (e.g. print or console.print)
        include_gnomad: If True, download gnomAD population frequency data (~1-2 GB)

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

    total_steps = 8 if include_gnomad else 6

    # Initialize database tables
    _log(f"[1/{total_steps}] Creating database tables...")
    db.initialize()

    # Download ClinVar (skip if already downloaded and >100MB)
    clinvar_path = data_dir / "variant_summary.txt.gz"
    if clinvar_path.exists() and clinvar_path.stat().st_size > 100_000_000:
        clinvar_mb = clinvar_path.stat().st_size / (1024 * 1024)
        _log(f"[2/{total_steps}] ClinVar already downloaded ({clinvar_mb:.0f} MB) — skipping download.")
    else:
        _log(f"[2/{total_steps}] Downloading ClinVar from NIH (~400 MB)... this may take a few minutes")
        download_file(CLINVAR_URL, str(clinvar_path), progress_callback, log=log)
        _log(f"[2/{total_steps}] ClinVar download complete.")

    # Parse ClinVar
    _log(f"[3/{total_steps}] Parsing ClinVar variants... (this takes 1-2 minutes)")
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
    if gwas_path.exists() and gwas_path.stat().st_size > 10_000_000:
        gwas_mb = gwas_path.stat().st_size / (1024 * 1024)
        _log(f"[4/{total_steps}] GWAS Catalog already downloaded ({gwas_mb:.0f} MB) — skipping download.")
        gwas_downloaded = True
    else:
        _log(f"[4/{total_steps}] Downloading GWAS Catalog from EBI... this may take a few minutes")
        try:
            download_file(GWAS_URL, str(gwas_zip_path), progress_callback, log=log)
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
                else:
                    # No TSV found — maybe the zip contains the data directly
                    zf.extractall(str(data_dir))
                    _log(f"       Extracted {len(zf.namelist())} files")
            # Clean up zip
            gwas_zip_path.unlink(missing_ok=True)
            gwas_downloaded = True
            _log(f"[4/{total_steps}] GWAS Catalog download complete.")
        except Exception as e:
            _log(f"       GWAS download failed: {e}")
            gwas_zip_path.unlink(missing_ok=True)

    # Parse GWAS (if downloaded)
    gwas_count = 0
    if gwas_downloaded:
        _log(f"[5/{total_steps}] Parsing GWAS associations...")
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

        if gnomad_path.exists() and gnomad_path.stat().st_size > 1_000_000:
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

    # Set metadata
    _log(f"[{total_steps}/{total_steps}] Finalizing database...")
    db.set_metadata("last_update", datetime.now().isoformat())
    db.set_metadata("clinvar_version", "latest")
    if gwas_downloaded:
        db.set_metadata("gwas_version", "latest")
    else:
        db.set_metadata("gwas_version", "unavailable")
    # Provenance from the manifest, not hardcoded — so the frequency layer is
    # version-agnostic and a source/version change is a data refresh.
    if include_gnomad and gnomad_downloaded:
        db.set_metadata("gnomad_source", str(gnomad_manifest.get("source", "gnomAD")))
        db.set_metadata("gnomad_version", str(gnomad_manifest.get("version", "unknown")))
    elif include_gnomad:
        db.set_metadata("gnomad_version", "unavailable")

    parts = [f"{clinvar_count:,} ClinVar"]
    if gwas_count > 0:
        parts.append(f"{gwas_count:,} GWAS")
    if gnomad_count > 0:
        parts.append(f"{gnomad_count:,} gnomAD")
    _log(f"Done! Database ready with {' + '.join(parts)} records.")
