# Input coverage and exclusions

Every nonblank, noncomment data row in a recognized input format receives one
final disposition. Ancestry's header and VCF headers are excluded from the row
denominator. Counts are shown in the CLI, web report, and exported HTML; the
[evidence JSON](evidence-export.md) also contains row numbers and dispositions.
Rows absent from the input cannot be counted. This is input-processing coverage,
not assay coverage, a negative genetic test, or a clinical sensitivity estimate.

| Disposition | Meaning |
| --- | --- |
| `malformed_row` | Missing columns or unusable row/header structure |
| `invalid_position` | Position is not a positive integer |
| `unsupported_identifier` | Identifier is unavailable or outside rsID lookup (including internal i-IDs) |
| `no_call` | Missing genotype, including partially missing VCF GT |
| `missing_genotype` | VCF lacks the required sample GT field |
| `unsupported_genotype` | VCF GT cannot be parsed, including unsupported ploidy/indices |
| `conflicting_input` | Same identifier has disagreeing parsed observations; all are excluded |
| `duplicate_row` | Additional exactly agreeing observation collapsed into the first |
| `failed_filter` | Parsed VCF observation explicitly fails FILTER or FORMAT/FT |
| `no_annotation` | No ClinVar/GWAS/PGx candidate in the installed references |
| `reference_or_no_applicable_annotation` | Matching left no applicable finding under the current reference filter |
| `rank_filtered` | Excluded by the default rank filter, including benign findings |
| `report_filtered` | Returned by analysis but removed by a report option such as traits-only |
| `reported` | Representative observation contributing a returned finding |
| `unaccounted` | A custom caller supplied inputs without corresponding analysis dispositions |

Rows have one disposition, chosen in processing order: parsing, identifier
support/conflicts, duplicate collapse, upstream filters, annotation/matching,
and report filters. For example, a duplicate of a failed-filter row is counted
as a duplicate; the representative row counts as failed. Missing annotations
refer to the installed data, not biological absence. The reference/no-applicable
category intentionally does not claim every excluded row is a verified reference
call. Legacy `benign_sites` and reference counters remain available; the new
rank/no-applicable names describe their broader filtering semantics.

Exact duplicate comparison includes chromosome, position, genotype, and all
retained VCF evidence (including phase, build declaration, and quality), but
ignores source line number. Different spellings are not normalized to establish
agreement. Conflicting parsed observations never use a last-row-wins rule.
The first agreeing row is the representative, and changing input order does not
change the resulting biological observation.

`coverage.counts` sums to `coverage.total_rows`; `accounted_rows` exposes the
number represented by dispositions. `complete` is false if accounting is missing
or any row is `unaccounted`. Library callers providing plain lists get the explicit
scope `parsed_inputs_only`; file parsers attach a row audit and use
`input_data_rows`. `returned_findings` is separate from input row counts. Old saved
reports have no fabricated coverage; rerun them to obtain it. Unrecognized files
still produce a parsing error rather than an invented denominator.
