# Offline VEP parsing comparison (issue #48)

`allelio import-vep manifest.json --output imported-vep` verifies and preserves
an existing **development** run. It does not execute VEP or download caches.
The resulting `benchmark.json` can be passed to `allelio benchmark ... --compare`.
Use a new output directory; inputs, raw JSON lines, logs and the original import
manifest are copied unchanged. Software and cache archives remain at their
original locations and must be retained separately.

The legacy `allelio-vep-import/1` recorded-review format remains supported for
development runs. The explicit `allelio-vep-internal-import/1` format records an
honestly attributed internal parsing alignment without claiming independent
approval. Both reject held-out imports. Synthetic VEP-shaped unit fixtures test
the importer; only an actual retained VEP execution supplies tool-run evidence.

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

Legacy comparisons pair only identical input/reference fingerprints. Every stage accepts
`unsupported`, which is excluded rather than counted as disagreement. Comparison
reports include per-stage paired, agreeing and excluded opportunity counts.
Whole-case exclusions contribute one exclusion to each stage; denominators are
case-stage opportunities, not patients or clinical sensitivity.

Internal parsing comparisons retain VEP's actual software/cache resource-set
digest separately from Allelio's actual database fingerprint. They pair differing
references **only for parsing**, when a synthetic/development declaration binds
those exact identities and identical input bytes. It explicitly states
`independent_validation=false`, `source_equivalence=false`, and parsing-only
scope. The input itself supplies the declared assembly checked by the importer.
No resource fingerprint is copied or altered to imply biological equivalence.
All other stages remain unsupported. These declarations record actual internal
preparation/review; they do not authenticate reviewers or prove historical execution.

## Pinned sparse-cache execution

The [execution protocol](../data/evaluation/vep-parsing-v2.protocol.json) freezes
VEP 116.3's exact official Linux arm64 image digest and archive, cache contents,
commands, inputs and denominators before case execution. Use the
[invented cases](../examples/vep-parsing/README.md): six shared cases/seven input
records, plus five deliberately outside this adapter's shared scope. Preserve
every actual exit status; a failed execution is an error, never a scope exclusion.
Allelio's reference database has one explicitly invented, off-input sentinel
needed for initialization, with no matching annotation for any input. It
isolates input handling and supplies no annotation-source comparison.

Ensembl's [upstream testing configuration](https://github.com/Ensembl/ensembl-vep/blob/f479099e2a9cd86887a48cf5c293fd7a208ddfb9/t/VEPTestingConfig.pm)
intentionally uses the sparse `84_GRCh38` test cache with current VEP code.
This is a historical, incomplete regression-test resource, not a current full
human cache. The published container omits test data, so extract the exact cache
from the separately pinned source archive. Keep version 84 explicit; do not
rename it to 116. Software/cache archives and raw annotation output stay local.

Code is Apache-2.0 upstream; Ensembl distinguishes its data from third-party
material. Cache metadata lists legacy COSMIC, HGMD-PUBLIC, SIFT and PolyPhen
sources. Do not infer blanket redistribution rights from VEP's software license.
Keep upstream notices and raw cache/output local; publish reviewed commands,
invented inputs, provenance hashes and parsing counts only. No plugins, custom
annotations, `--check_existing`, SIFT or PolyPhen options are activated.
See [software terms](https://www.ensembl.org/about/articles/software-license) and
[data disclaimer](https://www.ensembl.org/info/about/legal/disclaimer.html).

For reproduction, provision Docker separately, pull the protocol's exact arm64
image digest, and save it as `vep-116.3-arm64.tar` in a private resources directory
outside Git. Download the pinned source archive to
`ensembl-vep-f479099e.tar.gz`. Then:

```sh
python3 scripts/prepare_vep_smoke_resources.py \
  --resources "$VEP_RESEARCH_RESOURCES" --docker-context "$VEP_DOCKER_CONTEXT"
python3 scripts/run_offline_vep_smoke.py \
  --resources "$VEP_RESEARCH_RESOURCES" --docker-context "$VEP_DOCKER_CONTEXT" \
  --output "$VEP_NEW_LOCAL_RUN"
```

The preparer verifies OCI descriptors/blobs, image version/digest, original
source bytes, and every extracted cache file. It creates a dedicated cache volume
and refuses to overwrite one. The runner checks the installed cache inventory
before each case and after completion. Each container has networking disabled,
a read-only root filesystem/cache and no host mounts; invented input enters stdin.
The same pinned reference FASTA/index bytes are copied into private container
tmpfs and passed explicitly to VEP, permitting its lock/index writes without
changing the original cache. No source sequence or input allele is repaired.
Retain command arguments, inspected execution policy, output/logs, software/cache
archives, Allelio evidence, import and comparison artifacts. Public CI uses invented
unit fixtures only and does not download or execute VEP. No participant input is
used in this experiment.

Archive serialization can vary across Docker versions; the protocol's archive
hash identifies this retained artifact. A new export must still verify the same
OCI digest/blobs; document a new resource/protocol revision rather than replacing
recorded hashes. Source download archives can also change packaging; verify exact
files and disclose any revision. Retain the first run, including discrepancies.

The [first attempt](../data/evaluation/vep-parsing-v1.failed.json), using the
[original protocol](../data/evaluation/vep-parsing-v1.protocol.json), stopped after
one case with VEP exit 2: it could not create a FASTA lock inside the read-only
cache. Ten cases were not executed and no comparison was completed. Revision 2
corrects only that execution setup via the identical temporary FASTA copy.
Inputs, expectations, image and cache are unchanged. The original failure and
local artifacts are retained; this reuse is disclosed development work.

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

## Separate later scopes

Identity/source-retrieval comparisons need a new supported mapping against
appropriate aligned source snapshots, with explicit negatives and abstentions.
Genotype interpretation, consequence accuracy, representative production-cache
performance and explanation quality are not measured by parsing. Keep held-out
cases frozen until their separate genuine independent-review requirements are met.

VEP agreement is software/source agreement, not clinical ground truth. Issues
#45–47 track internal checks and paper claims separately from a later independent
study. Internal AI-assisted review is not independent scientific validation. See the
[independent evaluation package](independent-evaluation-package.md).

## Upstream format references

- [Ensembl VEP JSON output](https://www.ensembl.org/info/docs/tools/vep/vep_formats.html#json)
- [Offline/cache options](https://www.ensembl.org/info/docs/tools/vep/script/vep_options.html)
- [Custom annotation matching](https://www.ensembl.org/info/docs/tools/vep/script/vep_custom.html)
