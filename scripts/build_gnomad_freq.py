#!/usr/bin/env python3
"""Build a compact gnomAD frequency file for Allelio distribution.

This is a DEVELOPER tool — run it once on a machine with enough disk/bandwidth
to stream gnomAD VCF files. It produces a small gzipped TSV that end users
download during `allelio setup`.

The output contains only variants with rsIDs and their allele frequencies. To
keep the shipped file to a few MB (rather than hundreds), pass --array-sites
with a consumer-array rsID list (or a 23andMe / AncestryDNA raw file) so the
extract is trimmed to the ~1–2 M sites those chips actually report.

Usage:
    # Trim to a consumer-array rsID list (recommended — output is a few MB).
    # The rsID file may be a plain list, or a raw 23andMe / AncestryDNA export
    # (rsID is taken from the first column; comment lines are ignored).
    python scripts/build_gnomad_freq.py \\
        --array-sites arrays/23andme_v5.txt \\
        --output gnomad_v4.1.1_array_freq.tsv.gz

    # Use local VCF files you already downloaded
    python scripts/build_gnomad_freq.py --vcf-dir /path/to/vcfs \\
        --array-sites arrays/23andme_v5.txt --output gnomad_v4.1.1_array_freq.tsv.gz

    # Only process a few chromosomes (for testing)
    python scripts/build_gnomad_freq.py --chromosomes 21,22 --output gnomad_test_freq.tsv.gz

Publishing (see data/gnomad_manifest.json):
    1. Upload the output to the permaweb via Permavault (Arweave). gnomAD is
       CC0, so permanent redistribution is fine. The content-addressed URL
       never 404s — the failure that left this feature inert in v0.2.1.
    2. Mirror it on a GitHub Release as a fallback:
         gh release create v0.2.1-data gnomad_v4.1.1_array_freq.tsv.gz \\
             --title "gnomAD v4.1.1 array-site frequency data"
    3. Edit data/gnomad_manifest.json: set `version`, prepend the permaweb URL
       to `urls`, and set `sha256` to the digest this script prints. That
       manifest is the mutable pointer — bumping it is a data refresh, not a
       code change.

Requirements:
    pip install httpx
"""

import argparse
import gzip
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    httpx = None


# gnomAD genome sites VCF URL pattern (per chromosome). Both release/4.1/ and
# release/4.1.1/ exist on the public bucket; 4.1.1 is the current pin.
GNOMAD_VCF_TEMPLATE = (
    "https://storage.googleapis.com/gcp-public-data--gnomad"
    "/release/{version}/vcf/genomes/"
    "gnomad.genomes.v{version}.sites.{chrom}.vcf.bgz"
)

ALL_CHROMOSOMES = [f"chr{i}" for i in range(1, 23)] + ["chrX", "chrY"]

# VCF INFO fields to extract
FREQUENCY_FIELDS = {
    "AF": "af",
    "AF_grpmax": "af_grpmax",
    "AC": "ac",
    "AN": "an",
    "nhomalt": "nhomalt",
    "AF_afr": "af_afr",
    "AF_eas": "af_eas",
    "AF_fin": "af_fin",
    "AF_nfe": "af_nfe",
    "AF_sas": "af_sas",
}

# Output TSV column order
OUTPUT_COLUMNS = [
    "rsid", "AF", "AF_grpmax", "AC", "AN", "nhomalt",
    "AF_afr", "AF_eas", "AF_fin", "AF_nfe", "AF_sas",
]


def parse_info_field(info_str: str) -> dict:
    """Parse VCF INFO field into a dict of key=value pairs."""
    result = {}
    for item in info_str.split(";"):
        if "=" in item:
            key, value = item.split("=", 1)
            # For multi-allelic sites, take the first value
            if "," in value:
                value = value.split(",")[0]
            result[key] = value
    return result


def load_array_sites(path: str) -> set:
    """Load a set of consumer-array rsIDs to trim the extract to.

    Accepts either a plain rsID list (one per line) or a raw 23andMe /
    AncestryDNA export — the rsID is taken from the first whitespace/comma
    delimited column, and comment/header lines (starting with '#') are ignored.

    Args:
        path: Path to the rsID list or genotype file.

    Returns:
        A set of rsID strings (e.g. {"rs1234", "rs7412"}).
    """
    sites = set()
    with open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            token = line.replace(",", "\t").split("\t", 1)[0].strip()
            if token.startswith("rs"):
                sites.add(token)
    return sites


class _IterStream(io.RawIOBase):
    """Adapt a byte-chunk iterator into a readable binary stream.

    Lets us feed an HTTP response's chunks straight into gzip decompression
    without ever holding the whole (tens-of-GB) file — on disk or in memory.
    """

    def __init__(self, chunk_iter):
        self._it = chunk_iter
        self._buf = b""

    def readable(self):
        return True

    def readinto(self, b):
        while not self._buf:
            try:
                self._buf = next(self._it)
            except StopIteration:
                return 0
        n = min(len(b), len(self._buf))
        b[:n] = self._buf[:n]
        self._buf = self._buf[n:]
        return n


def iter_gzip_lines(chunk_iter):
    """Decode a gzip (or bgzip) byte-chunk iterator into text lines.

    bgzip files are a series of standard gzip members, so gzip.GzipFile reads
    them transparently. Nothing is buffered to disk.
    """
    raw = _IterStream(chunk_iter)
    buffered = io.BufferedReader(raw, buffer_size=1 << 20)
    gz = gzip.GzipFile(fileobj=buffered, mode="rb")
    return io.TextIOWrapper(gz, encoding="utf-8", errors="replace")


def emit_records(line_iter, output_file, count_so_far: int, array_sites: set = None) -> int:
    """Parse VCF lines and write frequency records to output.

    Shared by the local-file and streaming paths.

    Args:
        line_iter: Iterable of VCF text lines.
        output_file: Open gzip file handle to write TSV lines to.
        count_so_far: Running variant count for progress reporting.
        array_sites: If given, only write variants whose rsID is in this set
            (consumer-array trim). If None, write every variant with an rsID.

    Returns:
        Updated variant count.
    """
    count = count_so_far
    skipped = 0

    for line in line_iter:
        # Skip header lines
        if line.startswith("#"):
            continue

        fields = line.rstrip("\n").split("\t", 8)  # only split first 8 fields
        if len(fields) < 8:
            continue

        # fields[2] = ID. gnomAD may pack several rsIDs here ("rs1;rs2"),
        # so match each against the array set rather than trusting one.
        id_field = fields[2]
        rsids = [r for r in id_field.split(";") if r.startswith("rs")]
        if not rsids:
            skipped += 1
            continue

        if array_sites is not None:
            rsids = [r for r in rsids if r in array_sites]
            if not rsids:
                skipped += 1
                continue

        # fields[7] = INFO
        info = parse_info_field(fields[7])

        # Build the frequency values once; emit a row per matched rsID so a
        # multi-rsID site still lands under whichever ID the array reports.
        freq_values = []
        for col in OUTPUT_COLUMNS[1:]:  # skip rsid, already handled
            val = info.get(col, ".")
            freq_values.append(val if val else ".")

        for rsid in rsids:
            output_file.write("\t".join([rsid] + freq_values) + "\n")
            count += 1

        if count % 1_000_000 == 0:
            print(f"  ... {count:,} variants extracted (skipped {skipped:,})")

    print(f"  Chromosome done: {count - count_so_far:,} variants written, {skipped:,} skipped")
    return count


def process_vcf(vcf_path: str, output_file, count_so_far: int, array_sites: set = None) -> int:
    """Parse a gnomAD VCF already on disk and write frequency records."""
    # bgzipped files are gzip-compatible
    open_func = gzip.open if vcf_path.endswith((".gz", ".bgz")) else open
    with open_func(vcf_path, "rt", encoding="utf-8", errors="replace") as f:
        return emit_records(f, output_file, count_so_far, array_sites)


def stream_process_vcf(url: str, output_file, count_so_far: int, array_sites: set = None) -> int:
    """Stream a gnomAD VCF straight from the network — no full file on disk.

    Decompresses and parses on the fly, so peak disk stays near zero even for a
    40+ GB chromosome. This is the default when a local copy isn't present.
    """
    if httpx is None:
        print("ERROR: httpx is required for streaming. Install with: pip install httpx")
        sys.exit(1)

    timeout = httpx.Timeout(60.0, read=600.0)
    with httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        total_gb = total / (1024**3) if total else 0
        print(f"  Streaming {total_gb:.1f} GB (not saved to disk)...")
        lines = iter_gzip_lines(resp.iter_bytes(chunk_size=1 << 20))
        return emit_records(lines, output_file, count_so_far, array_sites)


def download_vcf(url: str, dest_path: str) -> bool:
    """Download a VCF file with progress reporting."""
    if httpx is None:
        print("ERROR: httpx is required. Install with: pip install httpx")
        sys.exit(1)

    print(f"  Downloading: {url}")
    try:
        timeout = httpx.Timeout(60.0, read=600.0)
        with httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            total_gb = total / (1024**3) if total else 0
            downloaded = 0
            last_pct = -1

            with open(dest_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=262144):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = int(downloaded * 100 / total) // 10 * 10
                        if pct > last_pct:
                            last_pct = pct
                            dl_gb = downloaded / (1024**3)
                            print(f"    {dl_gb:.1f} GB / {total_gb:.1f} GB ({pct}%)")

        print(f"  Download complete: {Path(dest_path).stat().st_size / (1024**3):.1f} GB")
        return True

    except Exception as e:
        print(f"  Download failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Build compact gnomAD frequency file for Allelio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output file path (e.g. gnomad_v4.1.1_array_freq.tsv.gz)",
    )
    parser.add_argument(
        "--vcf-dir",
        help="Directory containing already-downloaded gnomAD VCF files. "
             "If not specified, VCFs are downloaded to a temp directory.",
    )
    parser.add_argument(
        "--version",
        default="4.1.1",
        help="gnomAD version (default: 4.1.1). Also used as the release "
             "directory and VCF filename version on the public bucket.",
    )
    parser.add_argument(
        "--array-sites",
        help="Path to a consumer-array rsID list (or a raw 23andMe / "
             "AncestryDNA file) to trim the extract to. Strongly recommended — "
             "keeps the shipped file to a few MB instead of hundreds.",
    )
    parser.add_argument(
        "--chromosomes",
        help="Comma-separated list of chromosomes to process (default: all). "
             "Example: --chromosomes 21,22 for testing.",
    )
    parser.add_argument(
        "--cache-vcfs",
        action="store_true",
        help="Download each chromosome VCF to disk before processing, instead "
             "of streaming. Needs room for the largest chromosome (~40+ GB) but "
             "allows resuming. Default is to stream (near-zero disk).",
    )
    parser.add_argument(
        "--keep-vcfs",
        action="store_true",
        help="With --cache-vcfs, don't delete each VCF after processing.",
    )
    args = parser.parse_args()

    # Load the consumer-array trim set, if given.
    array_sites = None
    if args.array_sites:
        if not Path(args.array_sites).exists():
            print(f"ERROR: array-sites file not found: {args.array_sites}")
            sys.exit(1)
        array_sites = load_array_sites(args.array_sites)
        if not array_sites:
            print(f"ERROR: no rsIDs found in {args.array_sites}")
            sys.exit(1)
        print(f"Trimming to {len(array_sites):,} consumer-array rsIDs from {args.array_sites}")

    # Determine chromosomes to process
    if args.chromosomes:
        chroms = []
        for c in args.chromosomes.split(","):
            c = c.strip()
            if not c.startswith("chr"):
                c = f"chr{c}"
            chroms.append(c)
    else:
        chroms = ALL_CHROMOSOMES

    # Set up working directory for VCF files. Only needed when reading local
    # files (--vcf-dir) or caching downloads (--cache-vcfs); streaming needs no
    # scratch dir at all.
    if args.vcf_dir:
        vcf_dir = Path(args.vcf_dir)
        if not vcf_dir.exists():
            print(f"ERROR: VCF directory not found: {vcf_dir}")
            sys.exit(1)
    else:
        vcf_dir = Path("gnomad_vcf_tmp")
        if args.cache_vcfs:
            vcf_dir.mkdir(exist_ok=True)

    output_path = Path(args.output)
    print(f"Building gnomAD v{args.version} frequency file")
    print(f"Output: {output_path}")
    print(f"Chromosomes: {', '.join(chroms)}")
    print()

    total_variants = 0
    start_time = time.time()

    # Open output file (gzipped TSV)
    with gzip.open(str(output_path), "wt", encoding="utf-8", compresslevel=6) as out:
        # Write header
        out.write("## Allelio gnomAD frequency file\n")
        out.write(f"## Source: gnomAD v{args.version} genome sites VCFs\n")
        trim_note = f"{len(array_sites):,} array sites" if array_sites else "all rsIDs"
        out.write(f"## Trim: {trim_note}\n")
        out.write(f"## Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        out.write("\t".join(OUTPUT_COLUMNS) + "\n")

        for i, chrom in enumerate(chroms, 1):
            print(f"[{i}/{len(chroms)}] Processing {chrom}...")

            vcf_name = f"gnomad.genomes.v{args.version}.sites.{chrom}.vcf.bgz"
            vcf_path = vcf_dir / vcf_name
            url = GNOMAD_VCF_TEMPLATE.format(version=args.version, chrom=chrom)

            try:
                if vcf_path.exists():
                    # A local copy (from --vcf-dir or a prior --cache-vcfs run).
                    size_gb = vcf_path.stat().st_size / (1024**3)
                    print(f"  Using existing VCF ({size_gb:.1f} GB)")
                    total_variants = process_vcf(str(vcf_path), out, total_variants, array_sites)
                elif args.cache_vcfs:
                    # Opt-in: download the whole file to disk first (needs room
                    # for the largest chromosome, ~40+ GB), then process.
                    if not download_vcf(url, str(vcf_path)):
                        print(f"  Skipping {chrom} due to download failure")
                        continue
                    total_variants = process_vcf(str(vcf_path), out, total_variants, array_sites)
                    if not args.keep_vcfs and not args.vcf_dir:
                        print("  Removing VCF to free disk space...")
                        vcf_path.unlink(missing_ok=True)
                        vcf_path.with_suffix(".bgz.tbi").unlink(missing_ok=True)
                else:
                    # Default: stream from the network, nothing saved to disk.
                    total_variants = stream_process_vcf(url, out, total_variants, array_sites)
            except Exception as e:
                print(f"  Skipping {chrom} — error while processing: {e}")
                continue

            print()

    elapsed = time.time() - start_time
    output_size_mb = output_path.stat().st_size / (1024**2)

    # Checksum — this is the integrity value the downloader verifies against,
    # and (on the permaweb) the content that makes the URL address itself.
    print("Computing SHA-256 checksum...")
    digest = hashlib.sha256()
    with open(output_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    sha256 = digest.hexdigest()

    print("=" * 60)
    print(f"Done! Generated {output_path}")
    print(f"  Total variants: {total_variants:,}")
    print(f"  File size: {output_size_mb:.1f} MB")
    print(f"  SHA-256: {sha256}")
    print(f"  Time: {elapsed / 60:.1f} minutes")
    print()
    print("Next steps:")
    print("  1. Upload to the permaweb via Permavault (gnomAD is CC0). Copy the")
    print("     resulting Arweave/gateway URL.")
    print("  2. Mirror on a GitHub Release as a fallback:")
    print(f"       gh release create v0.2.1-data {output_path} \\")
    print(f'         --title "gnomAD v{args.version} array-site frequency data" \\')
    print(f'         --notes "gnomAD v{args.version} allele frequencies, '
          f'{total_variants:,} array rows, {output_size_mb:.1f} MB"')
    print("  3. Update data/gnomad_manifest.json to point at the new file:")
    print()
    manifest = {
        "schema": 1,
        "source": "gnomAD",
        "version": f"v{args.version}",
        "file": output_path.name,
        "sha256": sha256,
        "urls": [
            "<PERMAWEB_URL_HERE>",
            f"https://github.com/alexwbend/allelio/releases/download/"
            f"v0.2.1-data/{output_path.name}",
        ],
    }
    for line in json.dumps(manifest, indent=2).splitlines():
        print(f"     {line}")


if __name__ == "__main__":
    main()
