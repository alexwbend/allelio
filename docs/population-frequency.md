# Population frequency identity

A population frequency describes one allele at one position of one reference
build. Allelio shows a gnomAD frequency as the person's allele frequency, and
lets it move a finding's display rank, only when the record's identity agrees
with the identity of the allele the person carries. Nothing is lifted over,
strand-flipped, or guessed: a record that cannot be checked stays visible as
context and says why it was not used.

## What a record carries

Each gnomAD row in the local database is keyed by `(rsid, ref_allele,
alt_allele)` and carries `chromosome`, `position`, `assembly`,
`source_version`, the global and group frequencies, and counts. Several
alternate alleles at one rsID coexist (rs334 T>A and T>G each keep their own
row).

Two extract layouts exist:

- **Format 2** (`scripts/build_gnomad_freq.py` today): one row per alternate
  allele with chromosome, position, REF and ALT, and `## Format: 2`,
  `## Assembly: GRCh38`, `## Source: gnomAD v4.1.1 ...` header lines. Per-allele
  INFO values are split by allele index; a multiallelic site never receives
  another allele's number.
- **Format 1** (the extract published for 0.3.0): keyed by rsID alone, no
  allele, position or assembly, and the first alternate allele's values at a
  multiallelic site. A database built from it migrates in place; its rows keep
  empty alleles and no assembly and read as unverified context. `allelio info`
  records the loaded extract's format and assembly.

## How a record is checked

The allele the person carries is anchored on a checked source identity: the
ClinVar record the genotype matched (assembly, chromosome, VCF position, REF
and the matched ALT), or, failing that, declared VCF evidence for the site.
Consumer-array rows declare no build, so a GWAS- or PGx-only finding from one
has no anchor. Each gnomAD record at the rsID is then compared and labelled:

| `identity` | Meaning |
|---|---|
| `matched` | Assembly, chromosome, position, REF and ALT all agree. The only value that ranks or is described as this allele's frequency. |
| `unverified` | The record carries no allele (format 1), declares no assembly, or there is no anchor to compare against. |
| `build_mismatch` | The record is on a different assembly. |
| `position_mismatch` | Different chromosome or position on the same assembly. |
| `other_allele` | Same site, a different alternate allele; also when the matched allele is the site's reference allele, which no alternate-allele record describes. |
| `alleles_swapped` | The record's REF is the matched allele. |
| `orientation_reversed` | The record is the opposite-strand reading of the matched alleles. It is reported, not flipped; resolve it in the extract. |
| `allele_mismatch` | Neither allele agrees. |

`identity_note` says which. A finding's `gnomad_entry` is the one matched
record, or the only record at the rsID kept as flagged context, or null;
`gnomad_entries` holds every record with its label. The HTML report heads an
unverified record "Population Frequency (unverified, context only)" and the
AI prompt opens the frequency block with "Allele identity: NOT verified" and an
instruction not to draw a conclusion from it. Tier wording (common, uncommon,
rare) and the rule that frequency alone classifies nothing are unchanged, as is
the handling of missing or non-finite values.

## Refreshing the extract

Until a format 2 extract is published, the display adjustment is inert on the
published data and reports say so. Building one:

```bash
python3 scripts/build_gnomad_freq.py --array-sites arrays/23andme_v5.txt \
    --output gnomad_v4.1.1_array_freq.tsv.gz
```

Before it can be pointed at from `data/gnomad_manifest.json`, record there the
format (2), the assembly, the gnomAD release, the source VCF URLs, the SHA-256
the script prints, and gnomAD's CC0 terms. The test fixture
`tests/fixtures/example_gnomad.tsv.gz` was built in format 2 from gnomAD's
public API (`scripts/build_example_fixtures.py --gnomad-api`) with the dataset
and fetch date in its header.

Unsupported cases stay unresolved: no liftover between builds, no
normalisation of indel representations, no strand inference for frequency
records.
