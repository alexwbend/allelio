# Internal source-reference evaluation

This adapter evaluates the separately [frozen ClinVar reference set](clinvar-reference-set.md)
without changing its source records, constructed inputs, or expected outcomes.
The [execution protocol](../data/evaluation/clinvar-reference-evaluation-v1.protocol.json)
defines the diagnostic settings, measured fields, trace expectations, checks and
denominators before execution. This is internal source-fidelity evidence, not
independent clinical validation.

Source attribution: ClinVar, National Center for Biotechnology Information,
2026-09-03 snapshot, as pinned by the linked reference-set protocol. Attribute
ClinVar and its publication in any paper or downstream use of these results;
source data retains its own terms, separately from Allelio's MIT code license.

## Execution and trust boundary

From a source checkout, first reconstruct the exact reference set as documented
in the preparation guide. Then use a new local output directory:

```sh
python3 scripts/evaluate_clinvar_reference_set.py \
  --bundle tmp/clinvar-reference-v1 \
  --output tmp/clinvar-reference-evaluation-v1
```

By default, the checked-in preparation manifest supplies the trusted bytes for
the local bundle manifest. An explicit `--trusted-manifest` selects another
operator-reviewed trust anchor; it is not proof of an independent authority or
reviewer. Fixed artifact names, containment, regular files, checksums, record/case
identities, scalar domains, strata and complete nine-scenario coverage are checked
before output is created. Existing outputs and output paths inside the frozen
bundle are rejected. Missing or duplicated cases are errors, not exclusions.

The adapter materializes nine VCF batches, one per scenario, preserving the case
order and line-to-case mapping. Each case is scored as one VCF record with a
unique rsID within its batch. The single synthetic sample is an execution
container, not a plausible individual genome or an independent population
sample. Batch gene-grouping output is retained but is not scored here. All
sample labels say `SYNTHETIC_CONSTRUCTED`. Source
records are inserted into a new minimal ClinVar-only database. Other reference
sources remain empty. Each batch runs the production `record_run` path, including
VCF parsing, annotation and structured evidence export, with explanations off.
No setup/update, model discovery, model generation or reference download is used.

The fixed options are `include_benign=True`, `include_reference=True`, detailed
trace enabled, frequency adjustment off, traits-only off, and the unchanged
PGx threshold (no PGx records are loaded). These diagnostic settings expose
zero-copy observations that default reporting normally excludes. They do not
measure default finding selection, ranking, report usefulness or clinical safety.

## Observations and denominators

Every frozen case remains in the four frozen contract checks: parsed input,
filter exclusion, source-allele relationship, and source-ALT copy count. Actual
values come from the parser audit, returned findings and matching trace. Missing
findings are missing outputs, never inferred successful abstentions.

Four additional checks are specified before observing results:

- **Source-record fidelity:** compare allele/variation IDs, assembly, chromosome,
  VCF position, REF/ALT, gene, germline classification and review status against
  the frozen source record. The observed values come from the candidate trace
  and, where a finding is expected, the returned source entry.
  Only the predefined no-call scenario is inapplicable; a missing candidate in
  another scenario fails. Failed-filter cases still have a rejected candidate
  and remain applicable. HGNC ID and other omitted fields are not measured.
- **Trace contract:** verify the predefined decision, stage and reason for each
  scenario; no-call cases must have no candidate.
- **Observation accounting:** verify expected input, audit, finding, source-entry
  and candidate cardinalities. Extra or unmappable outputs also fail batch-level
  accounting and prevent an overall pass. Each batch also passes the production
  evidence schema and semantic-reference checks; broken document-local links
  fail overall success even when the allele contracts happen to match.
- **Row disposition:** require the observed no-call/failed-filter/reported path,
  rather than interpreting an absent finding as proof of correct handling.

Per-check opportunities, passes, failures and inapplicable counts are explicit.
A case passes only when all applicable checks pass. Overall success also requires
batch accounting. Report scenario and controlled source-stratum counts and the
number of source-record clusters whose nine cases all pass. These cases are
paired and clustered, not independent biological samples; no sampling-based
confidence interval, clinical sensitivity or pathogenicity-accuracy estimate is
computed.

## Local artifacts and public report

The output retains the constructed VCFs, complete evidence and run manifests,
minimal reference database, execution protocol and per-case results locally.
Code, input, reference and artifact integrity are checked before the final
`report.json` is installed, including the retained execution-protocol copy and
a digest of the exact per-case result bytes emitted by the writer. Full schema
validation errors stay local; the public report includes only their count.
A directory without that final report is incomplete;
an `INCOMPLETE` marker remains on failures before finalization. Interrupted
directories must not be reused or described as successful runs. A completed
report can legitimately say `passed=false`, preserving measured discrepancies.

Only the deliberately assembled aggregate report is a candidate public artifact.
It contains controlled metric labels, numeric counts, bounded runtime versions,
code/protocol/source fingerprints and artifact hashes. It does not copy arbitrary
source metadata, gene names, individual case IDs, trace notes, input paths,
environment variables or row-level observations. Review the actual report before
publication under the source/artifact policy; hashes are provenance, not
anonymization. Do not publish the local VCF, evidence, database or per-case files.

## First complete execution

The [aggregate report](../data/evaluation/clinvar-reference-v1.results.json) records
the first complete execution on 2026-10-21, using adapter/protocol commit
`447cc19` and the exact package, adapter, source and protocol hashes in that report.
All 66,492 constructed cases passed their applicable checks: 7,388 in each of
the nine scenarios, with all nine cases passing for each of the 7,388 source-record
clusters. All nine batches passed output accounting and evidence schema/semantic
validation, with no unexpected outputs or validation errors.

Source-record fidelity had 59,104 applicable opportunities; the 7,388 predefined
no-call cases were inapplicable for that check. Each other check had 66,492
opportunities. The execution used no participant genome, model or reference
download. The report preserves aggregate results and provenance hashes only;
the constructed inputs and detailed execution artifacts remain local.

These are internal contract results under the diagnostic settings above. They
do not estimate clinical accuracy, default report performance or independent
scientific validation. No frozen expectations were changed after this execution.

## Interpretation limits

The database bridge bypasses the production ClinVar TSV importer. Source-field
checks measure **selected-record → minimal database → production lookup/export**
round-trip fidelity, not end-to-end ClinVar ingestion accuracy. The selected
unambiguous GRCh38 autosomal SNPs and artificial genotypes do not establish
performance on indels, ambiguous source records, consumer arrays, participant
genomes, inheritance, PGx or model explanations. The existing synthetic benchmark
is unchanged and remains separate.

Retain the first complete report, including failures. If results inform a fix,
disclose the development reuse, retain original expectations/results, identify
the changed software, and record any later rerun separately. Never tune the
frozen set to make the implementation pass or call these cases unseen validation.
