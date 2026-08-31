#!/usr/bin/env python3
"""Build a compact gnomAD frequency file for Allelio distribution.

This is a DEVELOPER tool — run it once on a machine with enough disk/bandwidth
to download gnomAD VCF files. It produces a small gzipped TSV that end users
download during `allelio setup`.

The output file contains only variants with rsIDs and their allele frequencies.
It is typically 500 MB–1.5 GB gzipped, depending on the gnomAD version.

Usage:
    # Download gnomAD v4.1 genome VCFs and build the frequency file
    python scripts/build_gnomad_freq.py --output gnomad_v4.1_freq.tsv.gz

    # Use local VCF files you already downloaded
    python scripts/build_gnomad_freq.py --vcf-dir /path/to/vcfs --output gnomad_v4.1_freq.tsv.gz

    # Only process a few chromosomes (for testing)
    python scripts/build_gnomad_freq.py --chromosomes 21,22 --output gnomad_test_freq.tsv.gz

Once generated, upload the output file to a GitHub Release:
    gh release create v0.2.1-data gnomad_v4.1_freq.tsv.gz --title "gnomAD v4.1 frequency data"

Requirements:
    pip install httpx
"""

import argparse
import gzip
import os
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    httpx = None


# gnomAD v4.1 genome sites VCF URL pattern (per chromosome)
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


def process_vcf(vcf_path: str, output_file, count_so_far: int) -> int:
    """Stream-parse a gnomAD VCF and write frequency records to output.

    Args:
        vcf_path: Path to bgzipped VCF file
        output_file: Open gzip file handle to write TSV lines to
        count_so_far: Running variant count for progress reporting

    Returns:
        Updated variant count
    """
    count = count_so_far
    skipped = 0

    # bgzipped files are gzip-compatible
    open_func = gzip.open if vcf_path.endswith((".gz", ".bgz")) else open

    with open_func(vcf_path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            # Skip header lines
            if line.startswith("#"):
                continue

            fields = line.rstrip("\n").split("\t", 8)  # only split first 8 fields
            if len(fields) < 8:
                continue

            # fields[2] = ID (rsID)
            rsid = fields[2]
            if not rsid.startswith("rs"):
                skipped += 1
                continue

            # fields[7] = INFO
            info = parse_info_field(fields[7])

            # Build output line
            values = [rsid]
            for col in OUTPUT_COLUMNS[1:]:  # skip rsid, already added
                # Map output column name to INFO field name
                val = info.get(col, ".")
                values.append(val if val else ".")

            output_file.write("\t".join(values) + "\n")
            count += 1

            if count % 1_000_000 == 0:
                print(f"  ... {count:,} variants extracted (skipped {skipped:,} without rsID)")

    print(f"  Chromosome done: {count - count_so_far:,} variants with rsID, {skipped:,} skipped")
    return count


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
        help="Output file path (e.g. gnomad_v4.1_freq.tsv.gz)",
    )
    parser.add_argument(
        "--vcf-dir",
        help="Directory containing already-downloaded gnomAD VCF files. "
             "If not specified, VCFs are downloaded to a temp directory.",
    )
    parser.add_argument(
        "--version",
        default="4.1",
        help="gnomAD version (default: 4.1)",
    )
    parser.add_argument(
        "--chromosomes",
        help="Comma-separated list of chromosomes to process (default: all). "
             "Example: --chromosomes 21,22 for testing.",
    )
    parser.add_argument(
        "--keep-vcfs",
        action="store_true",
        help="Don't delete downloaded VCFs after processing each chromosome.",
    )
    args = parser.parse_args()

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

    # Set up working directory for VCF downloads
    if args.vcf_dir:
        vcf_dir = Path(args.vcf_dir)
        if not vcf_dir.exists():
            print(f"ERROR: VCF directory not found: {vcf_dir}")
            sys.exit(1)
    else:
        vcf_dir = Path("gnomad_vcf_tmp")
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
        out.write(f"## Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        out.write("\t".join(OUTPUT_COLUMNS) + "\n")

        for i, chrom in enumerate(chroms, 1):
            print(f"[{i}/{len(chroms)}] Processing {chrom}...")

            # Find or download VCF
            vcf_name = f"gnomad.genomes.v{args.version}.sites.{chrom}.vcf.bgz"
            vcf_path = vcf_dir / vcf_name

            if vcf_path.exists():
                size_gb = vcf_path.stat().st_size / (1024**3)
                print(f"  Using existing VCF ({size_gb:.1f} GB)")
            else:
                url = GNOMAD_VCF_TEMPLATE.format(version=args.version, chrom=chrom)
                if not download_vcf(url, str(vcf_path)):
                    print(f"  Skipping {chrom} due to download failure")
                    continue

            # Process VCF
            total_variants = process_vcf(str(vcf_path), out, total_variants)

            # Clean up downloaded VCF (unless --keep-vcfs)
            if not args.keep_vcfs and not args.vcf_dir:
                print(f"  Removing VCF to free disk space...")
                vcf_path.unlink(missing_ok=True)
                tbi_path = vcf_path.with_suffix(".bgz.tbi")
                tbi_path.unlink(missing_ok=True)

            print()

    elapsed = time.time() - start_time
    output_size_mb = output_path.stat().st_size / (1024**2)

    print("=" * 60)
    print(f"Done! Generated {output_path}")
    print(f"  Total variants: {total_variants:,}")
    print(f"  File size: {output_size_mb:.0f} MB")
    print(f"  Time: {elapsed / 60:.1f} minutes")
    print()
    print("Next step — upload to GitHub Releases:")
    print(f"  gh release create v0.2.1-data {output_path} \\")
    print(f'    --title "gnomAD v{args.version} frequency data for Allelio" \\')
    print(f'    --notes "Pre-processed gnomAD allele frequencies ({total_variants:,} variants, {output_size_mb:.0f} MB)"')


if __name__ == "__main__":
    main()
