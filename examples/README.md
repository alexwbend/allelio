# Example: analyzing a sample file

This directory has a small synthetic 23andMe-format file you can run through
Allelio right away, without needing your own DNA data, and a file that says
exactly what Allelio must find in it.

**`example_23andme.txt` is not real genetic data.** The rsIDs and positions
are real (GRCh37/hg19, as in a real 23andMe file), but the genotypes were
chosen by hand so that the file exercises every path the analysis has. It
describes no real person, which is why it is safe to commit and share.

## Run it

Assuming you've already installed Allelio and run `allelio setup` (see the
main [README](../README.md#getting-started) if not):

```bash
allelio analyze examples/example_23andme.txt --output examples/report.html
```

Open `examples/report.html` in a browser. Want to skip the AI explanations and
see the findings in a few seconds (no Ollama required)?

```bash
allelio analyze examples/example_23andme.txt --output examples/report.html --no-ai
```

Or try the web interface:

```bash
allelio serve
```

Then open **http://localhost:8080** and upload `examples/example_23andme.txt`.

## What you should see

[`expected_findings.json`](expected_findings.json) lists, for every line of
the example, whether Allelio reports it, with which zygosity and category, and
why. In short, the default run reports 13 sites and sets the rest aside:

| Site | Genotype | What it shows |
|---|---|---|
| `rs28897696` BRCA1 | GT | pathogenic allele, one copy |
| `rs1799963` F2 prothrombin | GA | pathogenic, one copy |
| `rs76763715` GBA1 N370S | TC | pathogenic, one copy (carrier for a recessive condition) |
| `rs334` HBB sickle cell | TA | ClinVar has two alleles at this rsID (T>A pathogenic, T>G likely benign); the one you carry is reported |
| `rs1800562` HFE C282Y | AA | pathogenic, **two copies** (the affected genotype for recessive hemochromatosis) |
| `rs3918290` DPYD*2A | CT | ClinVar "drug response", one copy → Pharmacogenomics |
| `rs1042713` ADRB2 | AG | drug response; a degenerate G/G row at the same rsID is ignored |
| `rs12913832`, `rs4988235` | GG, GA | ClinVar "association" rows (eye colour, lactase persistence) |
| `rs1805007`, `rs1805008` MC1R | CT, TT | conflicting classifications, still shown |
| `rs9939609` FTO | AT | GWAS-only site, one copy of the risk allele |
| `rs7412` APOE | CC | carries no copy of the ClinVar drug-response allele, so that row is set aside, but GWAS associations reported for the C allele remain |

Set aside or hidden, and counted in the output rather than silently dropped:

- **`rs6025` Factor V Leiden, `rs1800497`, `rs6311`** — genotypes carry no copy
  of the annotated allele. A database entry for an allele you do not have is
  not a finding; the CLI and report say "3 annotated positions where you carry
  only the reference allele were set aside".
- **`rs429358` APOE ε4, `rs1799945` HFE H63D** — one copy each, but the
  classification is "conflicting" and the variants are common, so the
  frequency adjustment pushes them past the benign cutoff. `--include-benign`
  shows them.
- **`rs762551`, `rs1042714`** — benign / likely benign.
- **two no-calls** (`--`), **two made-up rsIDs** in no database (most positions
  on a real chip are like this), and **one 23andMe internal `i`-ID row**,
  which is counted and disclosed but not looked up (see README: known gaps).

## Checking it

The test suite builds a small database from the real ClinVar, GWAS Catalog
and gnomAD rows for these rsIDs (`tests/fixtures/example_*`, extracted with
`scripts/build_example_fixtures.py`) and checks every expectation above on
every push (`tests/test_example_recall.py`). To check your own full database
does the same:

```bash
python3 scripts/check_example.py
```

## Building your own test file

The format is tab-separated: `rsid  chromosome  position  genotype`, with
`#`-prefixed comment lines allowed anywhere. Genotypes are on the forward
strand of the reference build, as 23andMe reports them; ClinVar's alleles are
too, so `expected_findings.json` was written by reading each site's ref/alt
from ClinVar and choosing the genotype to carry 0, 1 or 2 copies. See
[`allelio/parsers/twentythree.py`](../allelio/parsers/twentythree.py) for the
full parsing rules.
