# Evidence JSON Schema

The structured evidence export (`allelio analyze --json-output`, or **Export
Evidence JSON** in the web interface) has a machine-readable contract that
ships inside the package: `allelio/schemas/evidence-1.0.json`.

## Dialect and version

- Dialect: JSON Schema 2020-12 (`$schema` is
  `https://json-schema.org/draft/2020-12/schema`).
- One schema file per `schema_version` minor: `evidence-<major>.<minor>.json`.
  The document's `schema_version` names the version it was written against.
- The schema is available from an installed wheel:
  `allelio.schema.load_schema()` returns it, `allelio.schema.schema_path()`
  says where it is.

## Compatibility policy

Within a major version, fields are only added. Every object therefore allows
additional properties, and a consumer must ignore properties it does not know.
A field that is absent or `null` means unavailable, never zero, false, or
"none found". Enumerations (`identity`, `allele_match`, `classification_type`,
`decision`, `stage`, resolution `status`) may gain values in a minor version;
consumers should treat an unknown value as "unknown", not as an error.
Removing or retyping a field, or changing the meaning of an existing value, is
a major version change, and the file name changes with it.

A document at 1.x validates against the newest shipped 1.y schema with y at or
below x; the fields it adds beyond that schema are accepted as additional
properties.

## What the schema describes

`inputs` (parsed observations with optional VCF evidence), `findings` (every
returned finding, mirroring `VariantResult`), the source record types (ClinVar,
GWAS Catalog, gnomAD with its identity verdict, ClinGen, ClinPGx, and the
condition-level inheritance resolution), `gene_groups`, `provenance`,
`configuration`, `analysis_stats`, `coverage`, and `matching` (the candidate
trace, when present). Required and optional fields and their null semantics
are stated per object; `description` fields carry the meaning.

`input_id`, `finding_id` and `candidate_id` are local to one document. They
are indices, not identifiers: they are not VRS IDs, not normalised variant
identifiers, and two documents may use the same id for different things. The
genomic identity a record has is in its own fields (`assembly`, `chromosome`,
`position_vcf`, `ref_allele`, `alt_allele`, `allele_id`, and so on), and a
finding's `input_ids` links observations by rsID only, which verifies neither
build nor allele equivalence.

## Checks beyond JSON Schema

`allelio.schema.validate_evidence(document)` runs the structural validation
and then the checks a schema cannot express:

- Every `input_ids`, `finding_ids`, `finding_id`, and `candidate_ids`
  reference resolves inside the document; ids are well formed, unique, and
  ascending (`input-N` and `finding-N` contiguous; `candidate-N` ascending,
  since candidates at unlisted sites keep their number).
- A finding's referenced inputs share its rsID; only retained candidates
  support a finding; a rejected or unresolved candidate carries no
  `finding_id`.
- Gene group `indices` fall inside `findings` and `count` matches its
  distinct `finding_ids`.
- Coverage is conserved: `accounted_rows` equals the rows listed, `counts`
  equals the tally of listed row statuses, `accounted_rows` never exceeds
  `total_rows`, `returned_findings` equals the number of findings, and
  `complete` follows from the counts.
- Matching is conserved: `counts` and `by_source` sum to `candidate_count`,
  site `candidate_count`s sum to it, `listed_candidate_count` equals the
  candidates listed, a listed site enumerates exactly its candidates and an
  unlisted site's `candidate_ids` is null.

Every problem is one line naming the JSON location and what was expected, for
example `findings/0/input_ids: input_id 'input-9' does not exist in this
document`.

## Using it

```bash
allelio validate-evidence evidence.json
```

exits 0 when the file is valid and 1 with one line per problem otherwise. From
Python:

```python
from allelio.schema import validate_evidence_file
problems = validate_evidence_file("evidence.json")   # [] when valid
```

Other validators can load `allelio/schemas/evidence-1.0.json` directly for the
structural part; the reference and count checks above are Allelio's own.

## Fixtures

`tests/fixtures/evidence_schema/` holds small synthetic documents: a minimal
valid one (no inputs, no findings), a small valid one with a finding and a
matching trace, and invalid ones for a missing required section, a wrong
type, an unknown enumeration value, a dangling reference, unconserved
coverage counts, a finding supported by a rejected candidate, and a wrong
major version. `tests/test_evidence_schema.py` validates real CLI and web
exports (including empty results and a database without recorded releases),
each fixture, and the schema's presence in a built wheel.

This schema describes Allelio's export. It does not claim conformance to
GA4GH VRS, Phenopackets, or any other genomic standard.

Malformed structure returns validation errors before semantic checks run. The
semantic validator also checks reciprocal finding/candidate links, site rsIDs,
unique candidate ownership and per-decision totals across sites and sources.
