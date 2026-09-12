#!/usr/bin/env python3
"""Extract the reference-data rows behind examples/example_23andme.txt.

Reads the full ClinVar, GWAS Catalog, and gnomAD files that `allelio setup`
leaves under ~/.allelio/data and writes the rows for the example file's rsIDs
to tests/fixtures/, in the sources' own formats, so the test suite can build a
small real database and check the example's expected findings without a
network or a 2 GB download.

    python3 scripts/build_example_fixtures.py [--data-dir ~/.allelio/data]
    python3 scripts/build_example_fixtures.py --gnomad-api   # allele-aware gnomAD rows

The excerpts are tiny (a few hundred rows). ClinVar is public domain, gnomAD
is CC0, and the GWAS Catalog excerpt is used under EMBL-EBI's terms of use.

The gnomAD fixture needs allele identity (chromosome, position, REF, ALT and
the assembly) so the frequency checks in tests mean what they mean on a
refreshed extract. The extract published for 0.3.0 is keyed by rsID alone, so
``--gnomad-api`` asks gnomAD's public GraphQL API for every allele at each
example rsID instead and writes them in the format 2 layout of
scripts/build_gnomad_freq.py, with the dataset and fetch date in the header.
"""

import argparse
import gzip
import json
import os
import time
import urllib.request
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


def clingen_subset(src: Path, genes, dest: Path) -> int:
    """Keep the preamble and header, and the rows for the example's genes."""
    n = 0
    with open(src, "r", encoding="utf-8", errors="ignore") as f, open(dest, "w", encoding="utf-8") as out:
        for line in f:
            if line.startswith('"GENE SYMBOL"') or line.startswith('"+++') or not line.startswith('"'):
                out.write(line)
                continue
            if line.startswith('"CLINGEN') or line.startswith('"FILE CREATED') or line.startswith('"WEBPAGE'):
                out.write(line)
                continue
            gene = line.split(",", 1)[0].strip('"')
            if gene in genes:
                out.write(line)
                n += 1
    return n


def example_genes(clinvar_subset_path: Path):
    """Gene symbols named in the ClinVar excerpt (column GeneSymbol)."""
    genes = set()
    with open(clinvar_subset_path, encoding="utf-8") as f:
        next(f)
        for line in f:
            for g in line.split("\t")[4].split(";"):
                if g:
                    genes.add(g)
    return genes


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


GNOMAD_API = "https://gnomad.broadinstitute.org/api"
GNOMAD_API_DATASET = "gnomad_r4"  # gnomAD v4.1 genomes, GRCh38
# gnomAD's grpmax is the highest frequency among the continental genetic
# ancestry groups, excluding the bottlenecked and "remaining" groups.
GRPMAX_GROUPS = ("afr", "amr", "eas", "nfe", "sas")
POPULATION_COLUMNS = {"AF_afr": "afr", "AF_eas": "eas", "AF_fin": "fin", "AF_nfe": "nfe", "AF_sas": "sas"}


def _gnomad_api(query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    request = urllib.request.Request(
        GNOMAD_API, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "allelio-fixture-builder"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


def gnomad_from_api(rsids, dest: Path) -> int:
    """Write every gnomAD allele at each rsID, with identity, from the API."""
    search = "query($q: String!) { variant_search(query: $q, dataset: %s) { variant_id } }" % GNOMAD_API_DATASET
    detail = """query($id: String!) { variant(variantId: $id, dataset: %s) {
        variant_id reference_genome chrom pos ref alt rsids
        genome { ac an af homozygote_count populations { id ac an } } } }""" % GNOMAD_API_DATASET

    def fmt(value):
        return "." if value is None else f"{value:.6g}" if isinstance(value, float) else str(value)

    rows, assembly = [], None
    for rsid in rsids:
        hits = _gnomad_api(search, {"q": rsid})["variant_search"]
        for hit in hits:
            variant = _gnomad_api(detail, {"id": hit["variant_id"]})["variant"]
            if not variant or rsid not in (variant.get("rsids") or []) or not variant.get("genome"):
                continue
            assembly = assembly or variant["reference_genome"]
            genome = variant["genome"]
            by_group = {p["id"]: p for p in genome["populations"]}

            def group_af(group):
                p = by_group.get(group)
                return (p["ac"] / p["an"]) if p and p["an"] else None

            grpmax = max((group_af(g) or 0.0 for g in GRPMAX_GROUPS), default=None)
            rows.append([
                rsid, variant["chrom"], str(variant["pos"]), variant["ref"], variant["alt"],
                fmt(genome["af"]), fmt(grpmax), fmt(genome["ac"]), fmt(genome["an"]),
                fmt(genome["homozygote_count"]),
            ] + [fmt(group_af(g)) for g in POPULATION_COLUMNS.values()])
        time.sleep(0.2)  # be polite to the public API
    with gzip.open(dest, "wt", encoding="utf-8") as out:
        out.write("## Allelio gnomAD frequency file\n")
        out.write("## Format: 2\n")
        out.write(f"## Source: gnomAD v4.1 GraphQL API, dataset {GNOMAD_API_DATASET}, genomes\n")
        out.write(f"## Assembly: {assembly or 'GRCh38'}\n")
        out.write("## License: CC0 1.0 (gnomAD); redistribution permitted\n")
        out.write(f"## Trim: {len(rsids)} example rsIDs; AF_grpmax computed over {', '.join(GRPMAX_GROUPS)}\n")
        out.write(f"## Generated: {time.strftime('%Y-%m-%d')}\n")
        out.write("rsid\tchrom\tpos\tref\talt\tAF\tAF_grpmax\tAC\tAN\tnhomalt\tAF_afr\tAF_eas\tAF_fin\tAF_nfe\tAF_sas\n")
        for row in rows:
            out.write("\t".join(row) + "\n")
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.path.expanduser("~/.allelio/data"))
    ap.add_argument("--gnomad-api", action="store_true",
                    help="fetch allele-aware gnomAD rows from the public API instead of "
                         "subsetting the local extract; refreshes only the gnomAD fixture")
    args = ap.parse_args()
    if args.gnomad_api:
        n = gnomad_from_api(example_rsids(), FIXTURES / "example_gnomad.tsv.gz")
        print(f"gnomAD rows (API, allele-aware): {n}")
        return
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
    clingen_src = data / "clingen_gene_validity.csv"
    if clingen_src.exists():
        genes = example_genes(FIXTURES / "example_clinvar.tsv")
        n = clingen_subset(clingen_src, genes, FIXTURES / "example_clingen.csv")
        print(f"ClinGen rows: {n} (for {len(genes)} genes)")
    else:
        print("ClinGen file not found; run `allelio update` first to fetch it")


if __name__ == "__main__":
    main()
