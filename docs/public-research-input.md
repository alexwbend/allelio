# Bounded public research input demonstration

This experiment addresses input compatibility and conserved processing counts,
using a broadly consented public research genome. It does not evaluate clinical
accuracy or replace the separately constructed ClinVar source-reference checks.
The [frozen protocol](../data/evaluation/giab-input-v1.protocol.json) specifies the
source, region, reference database, normal reporting options and public boundary.

## Source and rights review

We selected NIST Genome in a Bottle (GIAB) HG002, v5.0q draft assembly-based
benchmark, GRCh38 `smvar` VCF. NIST's current project page supersedes HG002
v4.2.1 with this release. The official README, reviewed 2026-10-21, describes
NIST data-use terms permitting use and derivatives with acknowledgment and
applicable notices. The protocol pins the README and checksum document hashes.
Do not relabel the source as MIT or CC0; Allelio's code license is separate.

NIST describes broad PGP consent and encourages research publication. This does
not make HG002 anonymous. We use only the minimum dataset accession and exact
release provenance; do not link participant profiles, names or phenotype data.
Raw source, original headers/sample labels, selected rows, reports, detailed
evidence and logs must stay in controlled local storage outside Git, public CI
and hosted AI/development agents. A private directory reduces accidental access;
it is not encryption or a complete privacy guarantee. Check local backups too.

Sources: [GIAB project](https://www.nist.gov/programs-projects/genome-bottle),
[consent/use FAQ](https://www.nist.gov/programs-projects/faqs-genome-bottle),
[release README](https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/HG002_NA24385_son/v5.0q/NIST_HG002_v5.0q_variant-benchmarksets_README.md),
[NIST terms](https://www.nist.gov/open/license).

## Prespecified selection and execution

Select every VCF row with POS 20,000,001–21,000,000 inclusive on chromosome 22,
accepting `22`/`chr22` solely for selection. This fixed positional interval was
chosen before genotype access, independently of annotation yield. Stream the
whole compressed source; retain its complete original headers and selected row
bytes unchanged. Do not insert rsIDs, infer a build, normalize alleles, alter
sample labels, or remove unsupported rows. Record extraction date/nature locally
and acknowledge NIST. Position selection does not capture all boundary overlaps.

The production pipeline uses the previously frozen minimal ClinVar-only database
from the [reference evaluation](clinvar-reference-evaluation.md), identified by
its logical hash; other source tables are empty. It uses normal annotation
defaults, not the earlier diagnostic include-reference/include-benign settings.
Run `record_run` with explanations off, validate evidence, then replay annotation
and verify the conserved row counts and fingerprints. Python network connection
and DNS entry points are denied during processing. This does not prove isolation
from every possible process or operating-system networking mechanism.

The source `smvar` VCF includes structural variants. GIAB recommends its paired
BED for variant-call benchmarking. We deliberately perform a raw input-handling
demonstration without that BED intersection; we do not compute variant-call
precision/recall, pathogenicity accuracy, population estimates or clinical truth.

## Reproduction and artifacts

First reconstruct the exact minimal reference database using the linked reference
evaluation guide. Fetch the source from the protocol's exact URL into a private
directory **outside every Git checkout**. Verify the published MD5 (transport/
release consistency, not cryptographic authentication), compute SHA-256 and keep
the original README, checksum metadata and retrieval record. Preserve the NIST
notices. The runner checks the source MD5 and frozen database identity before use.
For example, with an existing private directory in `RESEARCH_INPUT_DIR`:

```sh
python3 scripts/demonstrate_public_input.py \
  --source "$RESEARCH_INPUT_DIR/HG002_GRCh38_v5.0q_smvar.vcf.gz" \
  --database tmp/clinvar-reference-evaluation-v1/references.db \
  --output "$RESEARCH_INPUT_DIR/run-v1"
```

Keep all output local until the aggregate `report.json` is reviewed. The runner
refuses existing output directories and inputs/outputs inside a Git checkout.
An absent final report means incomplete execution; a completed report may record
failed checks. Exceptions are deliberately generic at the terminal. Full errors
from the production path, if any, stay in the private execution log.

The candidate public report contains source/protocol/software fingerprints,
runtime versions, source/selected row counts, controlled identifier-syntax and
parser/final-disposition counts, returned-finding count, evidence validity and
annotation replay status. No row identities, genotypes, original metadata or
health interpretations are copied. Artifact hashes identify this retained run;
timestamps in local manifests mean not every artifact is byte-identical on rerun.
Hashes are provenance, not anonymization. Review the actual report before copying
it into the repository. CI tests must use invented inputs only.

Successful accounting/replay is separate from support for the input. Zero parsed
rows or zero findings cannot establish that the genome is benign, that annotation
is accurate, or that a negative genetic test occurred. A single chosen interval
does not establish whole-genome, consumer-array or population performance. Retain
the first result, including limitations; any identifier/build overlay or software
fix requires a separately named follow-up experiment with development reuse
disclosed. Do not replace the raw result with a repaired input.

Publication attribution should include the GIAB
[data resource](https://doi.org/10.1038/sdata.2016.25),
[benchmarking methods](https://doi.org/10.1038/s41587-019-0054-x),
README-recommended [Q100 work](https://doi.org/10.1101/2025.09.21.677443), and the
new [v5.0q benchmark preprint](https://doi.org/10.64898/2026.09.23.752440).
