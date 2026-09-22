# Offline VEP comparison preparation (issue #48)

`allelio import-vep manifest.json --output imported-vep` verifies and preserves
an existing **development** run. It does not execute VEP or download caches.
The resulting `benchmark.json` can be passed to `allelio benchmark ... --compare`.
Use a new output directory; inputs, raw JSON lines, logs and the original import
manifest are copied unchanged. Software and cache archives remain at their
original locations and must be retained separately.

This is the first, deliberately bounded part of #48. No real VEP run, approved
reference alignment, independent labels or human ratings are shipped. Synthetic
VEP-shaped unit fixtures test the importer, not VEP's actual behavior. Held-out
imports are rejected until an independently approved execution workflow exists.

## Supported comparison

Only parsing of single-sample VCFs with an explicit `##reference=GRCh37` or
`##reference=GRCh38`, unique rsIDs/positions, biallelic SNPs, fully called haploid
or diploid genotypes, and no failed site/sample filters is currently compared.
The `input` field from each VEP JSON row must match an original VCF record,
including coordinates, alleles, filter and sample fields. Repeated or foreign
output records fail the import. A successful run emitting at least one original
record is `parsed`; zero records is `excluded`, matching the existing coarse
case-level benchmark definition. It does **not** measure per-record recall or
assert that every input record was retained. Each supported case includes `parsing_counts` with input, emitted and omitted
record counts; unsupported cases have null counts. Raw output remains available
to inspect omissions. Conflicting or repeated reference declarations and malformed
VCF column headers are outside shared scope. Nonzero execution status is an import error, not an exclusion.

Consumer arrays, ambiguous builds, indels, multiallelic sites, missing genotypes,
filters and duplicate inputs are explicitly unsupported by this initial mapping.
Identifier recovery, allele identity matching, source selection and Allelio report
grouping are unsupported for every case. Neither a VEP consequence nor a
`colocated_variants` rsID proves Allelio's ClinVar identity/source-selection stage.
Explanations are outside the five-stage benchmark contract altogether.

Comparisons pair only identical input/reference fingerprints. Every stage accepts
`unsupported`, which is excluded rather than counted as disagreement. Comparison
reports include per-stage paired, agreeing and excluded opportunity counts.
Whole-case exclusions contribute one exclusion to each stage; denominators are
case-stage opportunities, not patients or clinical sensitivity.

## Import manifest

Paths are relative to the manifest and must remain inside its directory. Every
resource has a SHA-256 verified against its bytes. Pin software and cache archives
(or complete, immutable inventories of their installed contents), any custom
source files, and plugin code as resources. An inventory's hash only verifies the
inventory, so the operator must also verify installed contents against it before
execution. Resource versions should identify the exact releases, not `latest`.

Example shape below uses placeholders, **not** valid hashes or an approval:

```json
{
  "schema": "allelio-vep-import/1",
  "split": "development",
  "license": "Document the input's actual reuse terms",
  "vep_version": "EXACT_RELEASE",
  "assembly": "GRCh38",
  "hardware": "OS, CPU, RAM and execution environment",
  "resources": [
    {"kind": "software", "path": "vep.tar.gz", "version": "EXACT_RELEASE", "sha256": "SOFTWARE_SHA256"},
    {"kind": "cache", "path": "cache.tar.gz", "version": "EXACT_CACHE_RELEASE_AND_ASSEMBLY", "sha256": "CACHE_SHA256"}
  ],
  "plugins": [],
  "cases": [{
    "id": "development-snp",
    "input": {"path": "input.vcf", "sha256": "INPUT_SHA256"},
    "raw_output": {"path": "vep.jsonl", "sha256": "OUTPUT_SHA256"},
    "log": {"path": "vep.log", "sha256": "LOG_SHA256"},
    "command": ["vep", "--offline", "--cache", "--cache_version", "EXACT_RELEASE", "--dir_cache", "cache", "--assembly", "GRCh38", "--format", "vcf", "--json", "--input_file", "input.vcf", "--output_file", "vep.jsonl"],
    "exit_code": 0,
    "alignment": {
      "approved": true,
      "input_sha256": "INPUT_SHA256",
      "reviewer": "REVIEWER_SUPPLIED_ID",
      "date": "REVIEW_DATE",
      "rationale": "REVIEWER_AUTHORED_SCOPE_AND_REFERENCE_ALIGNMENT",
      "resource_sha256": ["SOFTWARE_SHA256", "CACHE_SHA256"],
      "allelio_references_sha256": "APPROVED_ALLELIO_LOGICAL_REFERENCE_SHA256"
    }
  }]
}
```

`plugins` must list exactly the hashes of resources whose `kind` is `plugin`,
without duplicates; it is empty when none were used. Software/cache hashes cannot
stand in for plugin code. Add
resources with versioned source identities for all custom annotations. Preserve
the actual command as separate argument strings and combined execution logs.
Do not fill in a reviewer identity or approval on their behalf. The reference
fingerprint is the `references.logical_sha256` from the approved Allelio run;
it must not be copied merely to make a comparison pair. The approval binds that
fingerprint to the complete VEP resource set and the exact input SHA-256. A
changed input requires a renewed approval declaration. The adapter
checks these declarations and file integrity; it cannot authenticate reviewers,
prove semantic alignment, verify historical execution, or prove network isolation.

## Remaining work before completing #48

1. Obtain reviewer approval for exact shared development cases and reference
   alignment, and provision pinned VEP/cache/plugin resources.
2. Run VEP offline on those approved cases, preserve raw artifacts, and validate
   this importer against actual output from that pinned version.
3. Define and independently approve allele-identity and source-retrieval mappings
   against aligned source snapshots. Extend scope with explicit negative and
   abstention cases; do not infer alignment from rsIDs or consequence names.
4. Keep held-out cases frozen until reviewer-authored expectations are locked.

VEP agreement is software/source agreement, not clinical ground truth. Issues
#45 and #46 still require independent reviewers and frozen cases; #47 depends on
those results and the completed comparison. See the
[independent evaluation package](independent-evaluation-package.md).

## Upstream format references

- [Ensembl VEP JSON output](https://www.ensembl.org/info/docs/tools/vep/vep_formats.html#json)
- [Offline/cache options](https://www.ensembl.org/info/docs/tools/vep/script/vep_options.html)
- [Custom annotation matching](https://www.ensembl.org/info/docs/tools/vep/script/vep_custom.html)
