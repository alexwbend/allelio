# ClinVar field mapping

Allelio reads ClinVar's `variant_summary.txt.gz`, the per-allele, per-assembly
summary NCBI publishes weekly. This page records which of its columns are
imported, what each one means, and what the file cannot say. Column positions
below are the documented ones; the parser reads the header row and finds each
column by name, so a file with columns added or reordered still maps.

## What one row is

One row is one ClinVar allele on one assembly. The classification is the
aggregate across every condition in `PhenotypeList`; the per-condition records
(RCVs) are listed by accession only. Their individual classifications are not
in this file, so Allelio keeps the accessions and says so rather than
inferring a per-condition call. When GRCh37 and GRCh38 rows exist for one
allele, the GRCh38 row is imported (the GRCh37 VCF-style alleles are not always
trustworthy); a GRCh37-only allele is imported as is. Rows without an rsID are
skipped.

Records are keyed by `(rsid, ref_allele, alt_allele, chromosome, allele_id)`.
The same AlleleID appears on X and Y in the pseudoautosomal region, and a few
alleles have distinct records under different AlleleIDs, sometimes with
different classifications; each is kept as its own record.

## Imported columns

| # | Column | Imported as | Meaning and handling |
|---|---|---|---|
| 1 | `#AlleleID` | `allele_id` | ClinVar allele identifier; part of the record key |
| 2 | `Type` | `variant_type` | Variant type as ClinVar writes it |
| 3 | `Name` | `name` | HGVS-style name |
| 5 | `GeneSymbol` | `gene` | `;`-separated when several genes overlap; the first is the record's gene |
| 6 | `HGNC_ID` | `hgnc_id` | Stable gene identifier where ClinVar gives one |
| 7 | `ClinicalSignificance` | `clinical_significance` | Aggregate classification, verbatim. Since the 2024 split this is the **germline** classification; see `classification_type` |
| 9 | `LastEvaluated` | `last_evaluated` | Date of the germline classification; `-` becomes null |
| 10 | `RS# (dbSNP)` | `rsid` | `-1` means none; the row is skipped |
| 12 | `RCVaccession` | `rcv_accessions` | `\|`-separated per-condition record accessions; kept verbatim, exposed as `rcv_list` |
| 13 | `PhenotypeIDS` | `condition_ids` | Identifiers per `PhenotypeList` entry, same order; MONDO ids drive [inheritance](inheritance.md). `''` when ClinVar gives none |
| 14 | `PhenotypeList` | `conditions` | Condition names, `\|`-separated, `;` inside an entry for co-occurring conditions |
| 15 | `Origin` | `origin` | Every reported origin, `;`-separated (`germline;somatic;unknown`) |
| 16 | `OriginSimple` | `origin_simple` | ClinVar's summary: `germline`, `somatic`, `germline/somatic`, `unknown`, `not provided`, `not applicable` |
| 17 | `Assembly` | `assembly` | `GRCh37` or `GRCh38`; other values are skipped |
| 19 | `Chromosome` | `chromosome` | Part of the record key |
| 25 | `ReviewStatus` | `review_status` | Review status of the germline classification; mapped to 0 to 4 stars for display only |
| 26 | `NumberSubmitters` | `number_submitters` | Submitters behind the aggregate |
| 31 | `VariationID` | `variation_id` | ClinVar variation identifier |
| 32 | `PositionVCF` | `position_vcf` | VCF-style position on `assembly` |
| 33 | `ReferenceAlleleVCF` | `ref_allele` | Forward-strand REF; `na` becomes `''` (not recorded) |
| 34 | `AlternateAlleleVCF` | `alt_allele` | Forward-strand ALT; `na` becomes `''` |
| 35 | `SomaticClinicalImpact` | `somatic_clinical_impact` | Separate somatic assertion; null when `-` or absent from the file |
| 36 | `SomaticClinicalImpactLastEvaluated` | `somatic_last_evaluated` | |
| 37 | `ReviewStatusClinicalImpact` | `somatic_review_status` | |
| 38 | `Oncogenicity` | `oncogenicity` | Separate oncogenicity assertion; null when `-` or absent |
| 39 | `OncogenicityLastEvaluated` | `oncogenicity_last_evaluated` | |
| 40 | `ReviewStatusOncogenicity` | `oncogenicity_review_status` | |

Not imported: `GeneID`, `ClinSigSimple`, `nsv/esv`, `ChromosomeAccession`,
`Start`, `Stop`, `ReferenceAllele`, `AlternateAllele` (the non-VCF allele
columns), `Cytogenetic`, `Guidelines`, `TestedInGTR`, `OtherIDs`,
`SubmitterCategories`, and the three `SCVsForAggregate...` columns.

## Classification type

`classification_type` says what `clinical_significance` is, from the file's
header, never assumed:

- `germline`: the file has the somatic columns, so column 7 is the aggregate
  germline classification.
- `unsplit`: the file predates the 2024 split; column 7 mixed germline and
  somatic assertions, and no later field separates them.
- `unknown`: the database was built before this column existed. Run
  `allelio update`.

A somatic clinical impact or oncogenicity assertion describes tumour tissue
and is reported beside the germline classification, never folded into it. A
record whose only assertion is somatic has `clinical_significance` of "no
classification for the single variant" and is not a germline finding.

## Three fields kept apart

For every ClinVar record a finding carries, three things a reader must not
conflate stay separate:

- `clinical_significance`: the source classification, verbatim.
- `allele_match` and `allele_match_note`: whether this person carries the
  allele the record is about (`carried` with the copy count, `unknown` with
  the reason, `absent`).
- `display_rank`: Allelio's presentation rank for the row, from the
  classification tier and review stars. Not a clinical score.

The HTML report shows the primary record's context on a "Classification
context" line and lists other records at the site with their own
classification and match; the web card carries the same in
`classification_context`; the AI prompt states the context per record and is
told not to merge records or present a somatic assertion as germline; the
evidence JSON carries every field.

## Migration

An existing database keeps its rows. A table keyed by allele alone is re-keyed
by record in place; columns the old table lacked stay null and read as
unknown until `allelio update` re-parses the source file. Nothing is
back-filled from assumptions.

## Fixtures

`tests/fixtures/clinvar_context/` holds synthetic rows in both layouts:
multiple conditions with several RCVs, a mixed germline and somatic record, a
record with missing fields, two distinct records for one allele with
different classifications, a pseudoautosomal X/Y pair, a somatic-only record,
and a pre-split file. `tests/test_clinvar_context.py` runs them through the
parser, the store (including migration), the analysis, and every surface.
