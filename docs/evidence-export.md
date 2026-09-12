# Structured evidence export, version 1.0

Use `allelio analyze example.txt --no-ai --json-output evidence.json` to save
JSON alongside the HTML report. In the web interface, choose **Export Evidence
JSON** after analysis. Older saved analyses require a new run to obtain evidence.
The export contains genetic observations; share it only as deliberately as the
original input file.

The top-level `schema_version` is `1.0`. Consumers must check the major version,
accept additive fields, and treat missing/null values as unavailable. A major
version change indicates incompatible field changes. JSON numbers are finite;
non-finite source numbers become null. A JSON Schema (2020-12) for the document
ships with the package, and `allelio validate-evidence evidence.json` checks a
file against it plus the reference and count rules a schema cannot express; see
[evidence schema](evidence-schema.md). The document contains:

- `software`, `generated_at`, `configuration`, `provenance`: software version,
  UTC time, analysis filters, and reference-source versions available locally.
- `inputs`: all parsed observations, including original VCF alleles, indices,
  phase, reference declaration, and quality evidence when available.
- `findings`: all returned findings, independent of the AI explanation limit.
  Fields mirror `VariantResult`: source entries (ClinVar, GWAS, gnomAD, ClinGen,
  PGx), category/rank, allele role/copies, strand decision, zygosity and inheritance
  notes. These are selected annotations, not every candidate database record.
  The additive `inheritance_resolution` field (and `inheritance` on each ClinVar
  entry) records how the inheritance phrase was reached: the resolution status,
  the ClinGen curations matched by MONDO identifier, the mapping method and
  version, the assertion's own conditions with their identifiers, and the
  gene-level summary kept separately. See [inheritance](inheritance.md).
  Each ClinVar entry carries its classification context (`classification_type`,
  `origin`, `origin_simple`, `rcv_accessions`, `number_submitters`, the somatic
  clinical impact and oncogenicity assertions with their review statuses and
  dates) and, separately from the source classification, `allele_match` with
  `allele_match_note` and Allelio's `display_rank`; every ClinVar record at the
  site is listed, distinct records included. See [ClinVar fields](clinvar-fields.md).
  `gnomad_entry` carries the frequency record's own identity (assembly,
  chromosome, position, REF, ALT, source version) and an `identity` label with
  `identity_note` saying whether it was verified as the matched allele's;
  `gnomad_entries` lists every record at the rsID. Only a `matched` record
  affected ranking. See [population frequency](population-frequency.md).
- `gene_groups`: the same groups as the report, with `finding_ids` references.
- `analysis_stats` and `limitations`: exclusion counts and interpretation limits.

`input_id` and `finding_id` are unique within a document. A finding's `input_ids`
references observations sharing its rsID; this linkage does not verify build or
allele equivalence. These IDs are not VRS IDs or normalized variant identifiers.
Raw VCF reference declarations are not certified genome assemblies. Null source
identity fields stay null. AI prose is excluded from this evidence document.

The additive `matching` field is the candidate-level selection trail: one
decision per reference record considered, with stage, reason code, source
identity, and document-local `candidate_id`; findings carry `candidate_ids` for
the records that support them. Its counts are over records, not rows or
findings. See [matching trace](matching-trace.md).

The additive `coverage` field records input row dispositions, including parsing
exclusions, when an audit is available. See [input coverage](input-coverage.md).
No annotation or an omitted finding must not be interpreted as a negative test.
