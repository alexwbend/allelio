# Audit of cloud PRs #32–#36

Reviewed 2026-09-12 against issues #22–#26 and the cumulative cloud head
`f71140c`. The cloud work adds useful condition, allele and source provenance,
but was not ready to merge without corrections.

## Verified defects corrected

- **Inheritance (#32):** matching one recessive condition did not prevent a
  definitive carrier label when other MONDO conditions were unmapped. Named
  conditions without identifiers also need an unresolved result. Known
  dominant/recessive conflicts remain visible. Mapping rules are now version 1.1.
- **Assertion scope (#32):** every secondary assertion inherited the leading
  assertion's gene curations. Each now uses its own genes; a conflicting
  pathogenic assertion prevents a site-wide carrier label.
- **Frequency anchor (#33):** unknown ClinVar calls retain an ALT for explanation,
  and that ALT could anchor a frequency despite failing VCF identity checks.
  Only carried alleles with compatible source identity can anchor frequency
  use. Differing source coordinates no longer select the first matching row.
- **Frequency storage (#33):** the `(rsid, REF, ALT)` key overwrote rows from
  different chromosomes, positions, builds or releases. The full source
  identity is now in the key, with migrations for both earlier layouts.
- **Upgrade reads (#33/#34):** old tables were queried with sort columns they
  did not contain. They can now be read before refresh. ClinVar migration also
  preserves chromosome and allele ID independently when only one exists.
- **ClinVar headers (#34):** missing optional columns could silently read a
  neighbouring column at a historical index. Named headers are authoritative;
  absent context remains unknown and missing required columns fail clearly.
- **Candidate trace (#35):** reference-only and frequency-only sites omitted
  frequency candidates; unresolved ClinVar calls could omit accompanying GWAS
  candidates. These paths are now recorded. ClinGen now traces every applicable assertion, retaining per-assertion
  source identities and resolution status under each curation candidate.
- **Evidence validation (#36):** malformed structures could crash semantic
  checks. They now return structural errors first. Semantic checks reject
  dangling support even with an empty candidate array, inconsistent reciprocal
  links, wrong-site references, duplicate site ownership and inconsistent
  decision totals.
- **Extract builder (#33):** a single per-allele value was reused for later
  alternate alleles. Missing values now stay missing. Array-site lists accept
  spaces as documented. Failed/incomplete chromosome runs return failure and
  retain a `.partial` file without replacing an existing extract or printing a
  publishable manifest/checksum.
- **Validation budget:** PR synchronization no longer launches the full CI
  matrix automatically. Opening, reopening, marking ready, main updates and
  explicit dispatch remain supported; CodeRabbit review requests are unaffected.

## Checks against actual data

A direct scan of `clinvar_variant_summary_2026-09-03.txt.gz` confirmed 43 columns
and **701 colliding GRCh38 `(rsID, REF, ALT)` keys**, accounting for 701 extra
records. The pathogenic BRCA1 rs28897696 row is G>T; the G>A row has a conflicting
classification. The APOE rs7412 source allele is C>T, so a risk allele C is the
reference allele and cannot use the alternate T frequency.

The BRCA1 pathogenic row names a dominant ClinGen condition but also several
unmapped MONDO conditions. The corrected aggregate therefore remains unresolved.
The example expectations also reflect unresolved CFTR, HFE and MC1R aggregates
with unmapped conditions; HFE C282Y no longer receives a definitive carrier
label from this aggregate. This is conservative source matching, not a new
clinical interpretation or a change to source classifications.

The existing 2.1 GB local database was queried read-only with the example input,
without migration or writes: 20 findings were returned. rs429358 and rs1799945
remain reported with unverified frequency context, as expected for format 1.

## Validation

The full local suite passed: **802 tests in 90.33 seconds**. One additional
format-2 database migration regression passed separately after that run; the
final test collection contains 803 tests. The suite includes CLI/web evidence
exports and installed-wheel schema access. Whitespace validation passed.

## Follow-through

The remaining partial ClinGen trace was completed. Unestablished relationships
and missing inheritance modes stay unresolved, and coverage now verifies that
each parsed input is counted exactly once. Evidence validation uses direct ID
lookups rather than repeatedly scanning whole input/candidate arrays. When
applicable pathogenic assertions disagree, the site headline stays conflicting
or unresolved; each record retains its own inheritance in reports and evidence.

Follow-through validation: the expanded full local suite passed **810 tests in
100.65 seconds**. Targeted report, web, inheritance, trace, schema and rebuild
regressions were rerun after the final headline correction.

A resumable three-worker rebuild is running under `build/gnomad-format2`, using
603,137 rsIDs recovered from the exact published legacy extract. Completed
chromosomes are checksummed and reused. The output is combined only after all
24 chromosomes complete. `scripts/validate_gnomad_release.py` checks the release
before upload. See `docs/gnomad-release.md` for the resumable procedure.

## Data release remains outstanding

The published 24 MB extract declares format 1 by omission and contains no allele
identity. It cannot safely be converted by attaching guessed alleles to its
frequencies. A new build from gnomAD source VCFs (or a verified completed build)
is still required before updating the Arweave object, release mirror and manifest.
The existing manifest and checksum remain valid and unchanged.

The upstream [gnomAD terms](https://github.com/broadinstitute/gnomad-browser/blob/main/browser/about/policies/terms.md)
were checked: primary exome/genome data use CC0; attribution and a browser link
are requested. The format-2 release must record the exact source URLs, assembly,
release, row count and checksum. Other licensed annotations are not part of
this frequency extract.

The five original PRs form a stack. Land their complete audited result together;
merging only an earlier layer does not include these audit corrections.
