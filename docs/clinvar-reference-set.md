# Internal ClinVar reference set

This protocol freezes source-derived expectations before an Allelio evaluation.
It does not run the annotator, contact a model, supply independent reviewer
labels, or measure clinical accuracy. The code and protocol implement issue #46.

## Scope frozen before execution

Version 1 uses the existing 2026-09-03 ClinVar snapshot, verified against the
SHA-256 in the protocol. Its original upstream location is rolling; obtain the
exact archived bytes named by the mirror and verify the checksum, rather than
substituting today's source. The date is the recorded snapshot date, not a claim
that the source remains current. No new source download is performed by the builder.

The header must explicitly contain the post-split germline/somatic fields.
`ReviewStatus` and `ClinicalSignificance` are the **germline** fields; somatic
impact and oncogenicity review statuses do not qualify a row. Select every
GRCh38 autosomal single-nucleotide variant meeting the protocol's exact review
status and classification lists, with numeric source identities/VCF position
and distinct single-base A/C/G/T REF and ALT. There is no result-based sampling.
Exclude any selected rsID appearing on more than one GRCh38 row in the full
source, even when the other row has a lower review status. GRCh37-only,
sex-chromosome, mitochondrial, multiallelic, indel, missing-identity and ambiguous
records are outside this deliberately bounded first set.

Minimal structured source records retain allele/variation IDs, rsID, assembly,
VCF coordinates/alleles, gene identifiers, germline classification and review
status. No submitted narrative, patient observation, or participant genome is
used. The selector reads the TSV directly instead of using Allelio's production
ClinVar parser or annotation output to generate its expectations.

For every selected reference record, freeze nine single-record VCF contracts:
reference (0/0), heterozygous (0/1), alternate (1/1), missing reference declaration,
deliberately wrong build, deliberately wrong position, incompatible alternate
allele, explicit failed filter, and no call (./.). Genotypes are constructed,
not measured in people. Expected source-ALT copy counts are arithmetic on the
constructed valid genotype; unavailable identity must stay unknown. The
wrong-build case is an intentional mismatch, not a liftover. These are expected
allele relationships, not stage outcomes inferred from the production annotator.

## Build and freeze

```sh
python3 scripts/prepare_clinvar_reference_set.py \
  --source clinvar_variant_summary_2026-09-03.txt.gz \
  --output tmp/clinvar-reference-v1
```

Use a new output directory. The builder verifies the source checksum before and
after selection and refuses to overwrite a frozen set. It emits the exact
protocol, `records.jsonl`, `cases.jsonl`, and a manifest containing their hashes,
builder hash, source identity, selection counts, strata, case counts, rights
record, and limitations. It records no local input paths, host names, environment
variables, or timestamps that would change artifact identity. Keep the complete
bundle; changing the protocol or builder requires a new set/revision and hashes.

The checked-in [v1 manifest](../data/evaluation/clinvar-reference-v1.manifest.json)
records selection from 9,049,133 source rows: 13,820 eligible rows, of which 6,432
were excluded by the all-GRCh38 rsID ambiguity rule, leaving 7,388 records.
These supply 66,492 constructed cases (nine per record), including benign,
uncertain and pathogenic source classifications. There are 7,384 expert-panel
records and four practice-guideline records. These are preparation counts, not
passed checks or independent samples. Neither selected rows nor cases are
included in Git; their hashes permit checking a local reconstruction.

The existing synthetic-only benchmark does **not** accept this external-source
set. Do not relabel reference-derived records as invented fixtures to bypass it.
An evaluation adapter must be separately reviewed, materialize the specified
single-record VCFs, preserve expectations, define actual-outcome mapping and
denominators, and record results/failures without changing this set. A frozen
set is not a passing result. Preserve the nine cases per source record as paired,
clustered observations rather than independent biological samples. Gene grouping, inheritance, PGx, consumer-array
measurement, general indels and explanation quality are not tested by v1.

## Rights, privacy, and publication

The source/artifact register is part of the protocol. Code is MIT; upstream data
is governed by its own terms. NCBI's molecular-data policy permits use and
distribution while explaining that it cannot transfer all submitter rights.
Attribute ClinVar and its publication; do not call all submitted data government
authored or automatically relicense it as MIT. Only the builder, protocol and
aggregate manifest/hashes are intended for Git in this change. The original
source, selected records and constructed cases stay local; review a proposed
derived-data release separately. Exact source retrieval and deterministic
construction permit reproduction without publishing a participant genome.

The public manifest must contain no participant identifiers, genotype observations,
individual health reports, private paths or credentials. Keep real-person data
separate from these constructed cases and out of public CI and hosted AI agents.
Reference source concordance cannot establish that a person's genotype or disease
classification is clinically correct. Selection and ambiguity exclusions limit
generalization; report denominators and failures, never clinical sensitivity.

Sources: [ClinVar review statuses](https://www.ncbi.nlm.nih.gov/clinvar/docs/review_status/),
[ClinVar use and attribution](https://www.ncbi.nlm.nih.gov/clinvar/docs/maintenance_use/),
[NCBI molecular-data policy](https://www.ncbi.nlm.nih.gov/home/about/policies/).
