# Candidate matching trace

The evidence JSON's `matching` section records what happened to every
reference record Allelio considered for an input site: retained, rejected, or
left unresolved, at which stage, with a structured reason code and the
identity the source gave the record. It is the selection trail behind the
`findings`, which list only what was kept.

## Where decisions come from

The matching functions record their own decisions as they make them; the
trace does not re-run a match. One decision per candidate record:

| Source | Stage(s) | Retained when | Rejected when | Unresolved when |
|---|---|---|---|---|
| ClinVar | filter, identity, allele, applicability | the genotype carries the record's allele (`allele_carried`) | the genotype carries no copy (`allele_absent`), the row names no allele of its own beside allele-specific rows (`haplotype_row_superseded`), or the VCF record failed its filter (`vcf_filter_failed`) | identity or allele could not be checked: `vcf_build_undeclared`, `source_identity_unavailable`, `build_mismatch`, `chromosome_mismatch`, `position_mismatch`, `mitochondrial_unsupported`, `allele_not_recorded`, `annotation_not_allele_specific`, `strand_ambiguous`, `genotype_allele_mismatch`, `genotype_no_call`, `non_snp_unsupported`, and the other VCF codes in `allelio/analysis/trace.py` |
| GWAS Catalog | allele, applicability | the genotype carries the risk allele (`risk_allele_carried`), or the association is shown with a ClinVar allele match (`reported_with_clinvar_match`) | no copy of the risk allele (`risk_allele_absent`) | the catalogue names no risk allele (`risk_allele_not_recorded`), or the genotype could not be judged |
| ClinPGx | level, applicability | the annotation row is written for this genotype (`pgx_genotype_matched`) | below the reporting level (`pgx_below_min_level`) or for another genotype (`pgx_other_genotype`) | no diploid SNP genotype (`genotype_unavailable`, `non_snp_unsupported`) |
| gnomAD | frequency | the record's identity agrees with the matched allele (`frequency_identity_matched`) | another allele, build, position, or orientation (`frequency_other_allele`, `frequency_build_mismatch`, ...) | no allele in the record or nothing to compare to (`frequency_identity_unverified`) |
| ClinGen | condition | the curation's MONDO identifier is named by the assertion (`condition_matched_by_mondo`) | it is not (`condition_not_named_by_assertion`), or the assertion has no identifiers (`assertion_has_no_condition_identifiers`) | |

`paths` in the section states, for every annotation path, what is traced.
A strand inference or an opposite-strand read is named in the note, never
silent.

## Document structure

```json
"matching": {
  "schema": "candidate-trace/1",
  "candidate_count": 41,
  "counts": {"rejected": 12, "retained": 25, "unresolved": 4},
  "by_source": {"clingen": {...}, "clinvar": {...}, ...},
  "sites_with_candidates": 17,
  "listed_candidate_count": 38,
  "detailed": false,
  "paths": {"clinvar": "traced: ...", ...},
  "sites": [{"rsid": "rs334", "input_ids": ["input-5"], "finding_id": "finding-5",
             "disposition": "reported", "candidate_count": 4,
             "counts": {"rejected": 1, "retained": 3}, "candidate_ids": ["candidate-9", ...],
             "candidates_listed": true}],
  "candidates": [{"candidate_id": "candidate-9", "rsid": "rs334", "source": "clinvar",
                  "identity": {"allele_id": "15333", "assembly": "GRCh38", "chromosome": "11",
                               "position_vcf": 5227002, "ref_allele": "T", "alt_allele": "A", ...},
                  "decision": "retained", "stage": "allele", "reason": "allele_carried",
                  "note": "1 copy of A", "finding_id": "finding-5"}]
}
```

Each finding also carries `candidate_ids`, the retained candidates that
support it. `candidate_id`, `finding_id` and `input_id` are local to one
document. A candidate's `identity` is whatever the source gave (ClinVar
allele and variation IDs, assembly, chromosome, position, REF and ALT; GWAS
study and risk allele; ClinPGx annotation and genotype; gnomAD alleles and
assembly; ClinGen disease and MONDO id); a rejected or unresolved candidate
keeps it, so the record can be looked up.

## Counts that must not be confused

- `matching.candidate_count` counts reference records considered.
- `coverage` counts input rows and their dispositions.
- `findings` (and `coverage.returned_findings`) count what was returned.

A site can have retained candidates and no finding: a benign match below the
default display cutoff, for instance. The site's `disposition` says which
later rule set it aside, and the candidate's `finding_id` is null.

## Size and the detailed export

On a whole-array file most annotated sites are reference genotype: the
person carries none of the annotated alleles, and every record there is
rejected as `allele_absent`. Those sites are always counted, but their
candidates are listed only with `allelio analyze --detailed-trace` (recorded
in `configuration.detailed_trace`). The web export uses the default form.

The trace records Allelio's matching decisions only. AI-generated text is
never part of it.
