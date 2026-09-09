# Example: analyzing a sample file

This directory has a small synthetic 23andMe-format file you can run through
Allelio right away, without needing your own DNA data.

**`example_23andme.txt` is not real genetic data.** The rsIDs are real
(chosen so ClinVar, GWAS Catalog, and gnomAD lookups all have something to
find), but every genotype was assigned at random. It reveals nothing about
any real person, which is why it's safe to commit to the repo and share.

## Run it

Assuming you've already installed Allelio and run `allelio setup` (see the
main [README](../README.md#getting-started) if not):

```bash
allelio analyze examples/example_23andme.txt --output examples/report.html
```

Open `examples/report.html` in a browser. You should see a handful of
findings — some from ClinVar (clinical significance), some from the GWAS
Catalog (trait associations), and gnomAD population frequencies adjusting
how common variants are ranked.

Want to skip AI explanations and just see the raw findings faster (no Ollama
required)?

```bash
allelio analyze examples/example_23andme.txt --output examples/report.html --no-ai
```

Or try the web interface instead of the CLI:

```bash
allelio serve
```

Then open **http://localhost:8080** and upload `examples/example_23andme.txt`.

## What's in the file

22 rows spanning a few different cases on purpose:

- **18 real, well-known rsIDs** that land in ClinVar, the GWAS Catalog, and/or
  gnomAD — e.g. the two APOE variants (`rs429358`, `rs7412`), the eye-color
  variant near `HERC2` (`rs12913832`), lactase persistence (`rs4988235`),
  Factor V Leiden (`rs6025`), and a DPYD pathogenic variant (`rs3918290`).
- **2 no-calls** (`--` genotype), to exercise the parser's no-call handling.
- **2 made-up rsIDs**, to show what happens with variants that aren't in any
  reference database — which is normal; most of the ~600k–1.8M positions on a
  real consumer chip aren't in any of these curated databases either.

Positions are GRCh37/hg19, matching what a real 23andMe file uses.

## Building your own test file

The format is tab-separated: `rsid  chromosome  position  genotype`, with
`#`-prefixed comment lines allowed anywhere. See
[`allelio/parsers/twentythree.py`](../allelio/parsers/twentythree.py) for the
full parsing rules (e.g. `rs`- and `i`-prefixed IDs, `--` no-calls).

**Never commit a real genotype file** — genomic data is immutable and
uniquely identifying. If you need more example variants, look up real rsIDs
and their GRCh37 coordinates (e.g. via
[dbSNP](https://www.ncbi.nlm.nih.gov/snp/) or
[myvariant.info](https://myvariant.info)) and pair them with a genotype you
pick at random.
