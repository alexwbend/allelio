# Structured evidence export, version 1.0

Use `allelio analyze example.txt --no-ai --json-output evidence.json` to save
JSON alongside the HTML report. In the web interface, choose **Export Evidence
JSON** after analysis. Older saved analyses require a new run to obtain evidence.
The export contains genetic observations; share it only as deliberately as the
original input file.

The top-level `schema_version` is `1.0`. Consumers must check the major version,
accept additive fields, and treat missing/null values as unavailable. A major
version change indicates incompatible field changes. JSON numbers are finite;
non-finite source numbers become null. The document contains:

- `software`, `generated_at`, `configuration`, `provenance`: software version,
  UTC time, analysis filters, and reference-source versions available locally.
- `inputs`: all parsed observations, including original VCF alleles, indices,
  phase, reference declaration, and quality evidence when available.
- `findings`: all returned findings, independent of the AI explanation limit.
  Fields mirror `VariantResult`: source entries (ClinVar, GWAS, gnomAD, ClinGen,
  PGx), category/rank, allele role/copies, strand decision, zygosity and inheritance
  notes. These are selected annotations, not every candidate database record.
- `gene_groups`: the same groups as the report, with `finding_ids` references.
- `analysis_stats` and `limitations`: exclusion counts and interpretation limits.

`input_id` and `finding_id` are unique within a document. A finding's `input_ids`
references observations sharing its rsID; this linkage does not verify build or
allele equivalence. These IDs are not VRS IDs or normalized variant identifiers.
Raw VCF reference declarations are not certified genome assemblies. Null source
identity fields stay null. AI prose is excluded from this evidence document.

Version 1.0 captures parsed observations, not rows discarded by parsing. No
annotation or an omitted finding must not be interpreted as a negative test.
