"""Download and parse reference databases."""

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


CLINVAR_URL = "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz"

# GWAS URL — verified from https://www.ebi.ac.uk/gwas/docs/file-downloads (Feb 2026)
# This returns a zip file containing the associations TSV
GWAS_URL = "https://www.ebi.ac.uk/gwas/api/search/downloads/associations/v1.0?split=false"

BATCH_SIZE = 10000


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
    log: Optional[Callable] = None
) -> None:
    """Orchestrate full download, parse, and index of reference databases.

    Args:
        db: AllelioDB instance
        data_dir: Directory to store downloaded files. Defaults to ~/.allelio/data/
        progress_callback: Optional callback function for progress updates
        log: Optional function to print status messages (e.g. print or console.print)

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

    # Initialize database tables
    _log("[1/6] Creating database tables...")
    db.initialize()

    # Download ClinVar (skip if already downloaded and >100MB)
    clinvar_path = data_dir / "variant_summary.txt.gz"
    if clinvar_path.exists() and clinvar_path.stat().st_size > 100_000_000:
        clinvar_mb = clinvar_path.stat().st_size / (1024 * 1024)
        _log(f"[2/6] ClinVar already downloaded ({clinvar_mb:.0f} MB) — skipping download.")
    else:
        _log("[2/6] Downloading ClinVar from NIH (~400 MB)... this may take a few minutes")
        download_file(CLINVAR_URL, str(clinvar_path), progress_callback, log=log)
        _log("[2/6] ClinVar download complete.")

    # Parse ClinVar
    _log("[3/6] Parsing ClinVar variants... (this takes 1-2 minutes)")
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
    _log(f"[3/6] ClinVar complete: {clinvar_count:,} records loaded.")

    # Download GWAS (skip if already downloaded and >10MB, otherwise try multiple URLs)
    gwas_path = data_dir / "gwas_associations.tsv"
    gwas_zip_path = data_dir / "gwas_associations.zip"
    gwas_downloaded = False
    if gwas_path.exists() and gwas_path.stat().st_size > 10_000_000:
        gwas_mb = gwas_path.stat().st_size / (1024 * 1024)
        _log(f"[4/6] GWAS Catalog already downloaded ({gwas_mb:.0f} MB) — skipping download.")
        gwas_downloaded = True
    else:
        _log("[4/6] Downloading GWAS Catalog from EBI... this may take a few minutes")
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
            _log("[4/6] GWAS Catalog download complete.")
        except Exception as e:
            _log(f"       GWAS download failed: {e}")
            gwas_zip_path.unlink(missing_ok=True)

    # Parse GWAS (if downloaded)
    gwas_count = 0
    if gwas_downloaded:
        _log("[5/6] Parsing GWAS associations...")
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
        _log(f"[5/6] GWAS complete: {gwas_count:,} records loaded.")
    else:
        _log("[4/6] ⚠ GWAS Catalog download failed from all sources.")
        _log("[5/6] Skipping GWAS parsing — ClinVar data is still available.")
        _log("       You can retry later with: allelio update")

    # Set metadata
    _log("[6/6] Finalizing database...")
    db.set_metadata("last_update", datetime.now().isoformat())
    db.set_metadata("clinvar_version", "latest")
    if gwas_downloaded:
        db.set_metadata("gwas_version", "latest")
    else:
        db.set_metadata("gwas_version", "unavailable")

    if gwas_count > 0:
        _log(f"Done! Database ready with {clinvar_count:,} ClinVar + {gwas_count:,} GWAS records.")
    else:
        _log(f"Done! Database ready with {clinvar_count:,} ClinVar records.")
        _log("       GWAS data can be added later with: allelio update")
