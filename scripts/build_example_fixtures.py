#!/usr/bin/env python3
"""Extract the reference-data rows behind examples/example_23andme.txt.

Reads the full ClinVar, GWAS Catalog, and gnomAD files that `allelio setup`
leaves under ~/.allelio/data and writes the rows for the example file's rsIDs
to tests/fixtures/, in the sources' own formats, so the test suite can build a
small real database and check the example's expected findings without a
network or a 2 GB download.

    python3 scripts/build_example_fixtures.py [--data-dir ~/.allelio/data]

The excerpts are tiny (a few hundred rows). ClinVar is public domain, gnomAD
is CC0, and the GWAS Catalog excerpt is used under EMBL-EBI's terms of use.
"""

import argparse
import gzip
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "example_23andme.txt"
FIXTURES = ROOT / "tests" / "fixtures"

GWAS_ROWS_PER_RSID = 4  # enough to carry several traits and a risk allele
# ...plus one row for every distinct risk allele the catalogue names at the
# site, so the fixture makes the same strand decisions as the full catalogue.


def example_rsids():
    ids = []
    for line in EXAMPLE.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        rsid = line.split("\t")[0]
        if rsid.startswith("rs"):
            ids.append(rsid)
    return ids


def clinvar_subset(src: Path, rsids, dest: Path) -> int:
    wanted = {r[2:] for r in rsids}
    n = 0
    with gzip.open(src, "rt", encoding="utf-8") as f, open(dest, "w", encoding="utf-8") as out:
        header = f.readline()
        out.write(header)
        for line in f:
            fields = line.split("\t", 10)
            if len(fields) > 9 and fields[9] in wanted:
                out.write(line)
                n += 1
    return n


def gwas_subset(src: Path, rsids, dest: Path) -> int:
    wanted = set(rsids)
    per = {r: 0 for r in rsids}
    alleles_seen = {r: set() for r in rsids}
    n = 0
    with open(src, "r", encoding="utf-8", errors="ignore") as f, open(dest, "w", encoding="utf-8") as out:
        header = f.readline()
        out.write(header)
        cols = header.rstrip("\n").split("\t")
        i_snps = cols.index("SNPS")
        i_cur = cols.index("SNP_ID_CURRENT")
        i_risk = cols.index("STRONGEST SNP-RISK ALLELE")
        for line in f:
            fields = line.rstrip("\n").split("\t")
            if len(fields) <= max(i_snps, i_cur, i_risk):
                continue
            rsid = fields[i_snps].strip()
            if rsid not in wanted:
                cur = fields[i_cur].strip()
                rsid = "rs" + cur if cur and not cur.startswith("rs") else cur
                if rsid not in wanted:
                    continue
            allele = fields[i_risk].strip().split("-")[-1].upper()
            new_allele = allele.isalpha() and allele not in alleles_seen[rsid]
            if per[rsid] >= GWAS_ROWS_PER_RSID and not new_allele:
                continue
            if per[rsid] >= GWAS_ROWS_PER_RSID - 1 and not allele.isalpha():
                continue
            out.write(line)
            if allele.isalpha():
                alleles_seen[rsid].add(allele)
            per[rsid] += 1
            n += 1
    return n


def gnomad_subset(src: Path, rsids, dest: Path) -> int:
    wanted = set(rsids)
    n = 0
    with gzip.open(src, "rt", encoding="utf-8") as f, gzip.open(dest, "wt", encoding="utf-8") as out:
        header = f.readline()
        out.write(header)
        for line in f:
            if line.split("\t", 1)[0] in wanted:
                out.write(line)
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.path.expanduser("~/.allelio/data"))
    args = ap.parse_args()
    data = Path(args.data_dir)
    FIXTURES.mkdir(exist_ok=True)
    rsids = example_rsids()
    print(f"{len(rsids)} rsIDs in {EXAMPLE.relative_to(ROOT)}")
    n = clinvar_subset(data / "variant_summary.txt.gz", rsids, FIXTURES / "example_clinvar.tsv")
    print(f"ClinVar rows: {n}")
    n = gwas_subset(data / "gwas_associations.tsv", rsids, FIXTURES / "example_gwas.tsv")
    print(f"GWAS rows: {n}")
    n = gnomad_subset(data / "gnomad_freq.tsv.gz", rsids, FIXTURES / "example_gnomad.tsv.gz")
    print(f"gnomAD rows: {n}")


if __name__ == "__main__":
    main()
