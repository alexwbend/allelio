# Condition-specific inheritance

ClinGen curates gene-disease pairs, each with its own mode of inheritance, and
one gene can carry a dominant and a recessive curation at once (GBA1: Parkinson
disease AD, Gaucher disease AR). The gene alone therefore cannot say whether one
copy of an allele is carrier status. Allelio resolves inheritance against the
condition the ClinVar assertion names, and keeps the gene-level summary beside
it as context.

## How a condition is matched

ClinVar's `PhenotypeIDS` column carries identifiers for each entry of
`PhenotypeList`, in the same order. Allelio keeps that column verbatim
(`condition_ids` on every ClinVar record and finding) and pairs it with the
names entry by entry. A ClinGen curation matches when its MONDO identifier
equals one the assertion carries. Names are never compared; nothing is inferred
from similarity.

The rule is recorded on every resolution as `mapping`:

```json
{"method": "mondo-exact", "version": "1.0"}
```

`CONDITION_ALIASES` in `allelio/analysis/inheritance.py` is the only place an
explicit equivalence between two MONDO identifiers can be added, after checking
both sources. It is empty in this release. Changing the rule or the table bumps
the version.

## What a resolution says

`inheritance_resolution` on a finding (and `inheritance` on each applicable
ClinVar entry) carries:

| Field | Meaning |
|---|---|
| `status` | `resolved`, `conflicting`, `unmapped`, `no_identifiers`, `identifiers_not_stored`, `not_established`, `not_curated` |
| `inheritance`, `note` | The display phrase and its provenance, the same text the HTML report, web view, CLI table, AI prompt, and evidence JSON show |
| `condition`, `condition_id` | The matched ClinGen disease and MONDO identifier when resolved |
| `matched` | Every ClinGen curation the assertion's identifiers matched, so a conflict stays visible |
| `conditions` | The assertion's conditions as ClinVar names them, each with its identifiers |
| `unmatched_condition_ids` | MONDO identifiers ClinGen has no curation for in this gene |
| `gene_inheritance`, `gene_note` | The gene-level summary, kept separately; it never decides the carrier label |

Statuses other than `resolved` mean the carrier rule did not apply:

- `conflicting`: the assertion names conditions ClinGen inherits differently
  (GBA1 with Gaucher disease and Parkinson disease). Which condition the allele
  causes is not decided here.
- `unmapped`: the assertion carries MONDO identifiers, but none is a ClinGen
  curation for the gene.
- `no_identifiers`: ClinVar gives no MONDO identifier (for example, only
  "not provided").
- `identifiers_not_stored`: the local database predates the `condition_ids`
  column. Run `allelio update`.
- `not_established`: the matched curation is Limited, Disputed, Refuted, or
  "No Known Disease Relationship".
- `not_curated`: ClinGen has no curation for the gene.

## The carrier rule

A finding is filed under **Carrier Status** only when its ClinVar
classification is pathogenic or likely pathogenic, the person carries exactly
one copy of the annotated allele, and the resolution is `resolved` to autosomal
recessive, or to X-linked on a diploid genotype (a single-letter genotype is
hemizygous, so one copy is the affected genotype). A gene curated for a
dominant and a recessive condition yields carrier status only when the
assertion names the recessive one alone.

These remain presentation rules over source curations. They do not establish
affected status, penetrance, symptoms, or biological sex.

## Fixtures

`tests/fixtures/challenge_inheritance/` holds synthetic ClinVar and ClinGen
files (invented genes, diseases, identifiers, and rsIDs, in the real formats)
covering a gene with dominant and recessive conditions, missing identifiers, a
disputed relationship, multiple conditions, an unmapped condition, an
unambiguous recessive case, an X-linked case, and a legacy database.
`tests/test_inheritance.py` runs them through the real parsers and analysis.
