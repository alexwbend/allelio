# Stage-by-stage developmental benchmark

Run the intentionally synthetic versioned challenge bundle locally:

```sh
allelio benchmark examples/challenges/bundle.json --output /tmp/allelio-benchmark
```

Use a new output directory each time. The bundle declares its synthetic status,
MIT reuse terms, reference rows, input files and expected stage outcomes. Bundle
resource paths must remain inside the bundle directory. No arbitrary builder
code or external tool is executed. The benchmark creates a temporary reference
database and invokes the actual recorded-run pipeline for every case.

Challenges cover consumer-array, Ancestry and VCF formats, no-calls, record
filters, duplicate conflicts, unknown build identity, condition inheritance,
multiallelic frequencies, successful probe recovery and missing-context abstention.
Each case has an explicit expectation for parsing, identifier recovery, identity
matching, source selection and reporting. Additional field checks verify the
inheritance category and selected frequency allele rather than just record counts.

`benchmark.json` links each case to its local run manifest and SHA-256, input and
reference fingerprints, source releases, actual outcomes and failed checks.
Per-stage denominators are **case-stage opportunities**, not patients or variants.
Correct abstentions/exclusions are contract matches but remain separate from
matched/selected/reported outcomes. Unsupported and inapplicable opportunities
are explicit. Incorrect attributions are failed contracts that nevertheless
recovered, matched, selected or reported a result. The CLI fails if any contract
check differs; this is a regression alarm, not a clinical performance score.

## Bounded comparison

`--compare other-report.json` accepts another tool's export in the documented
`allelio-benchmark/1` shape (`tool` name/version and cases with IDs, input/reference
fingerprints and per-stage `outcomes`). A comparison only pairs cases with equal
input and installed-reference fingerprints and stages supported by both tools.
Missing cases, different references and unsupported scope are listed as exclusions.
The comparison records tool versions and raw agreement denominators. Producing
another tool's aligned export is a separate, explicit adapter task; the benchmark
does not guess alignment from rsIDs or run another program automatically.

The development-only [`import-vep` adapter](vep-comparison.md) preserves frozen
offline VEP output and currently maps only a narrow VCF parsing scope. Every
stage accepts `unsupported`; these opportunities are excluded, not failures.
Comparison exports also report paired, agreeing and excluded counts per stage.

The fixtures are public invented developmental cases, not held-out patients or
independent clinical reference material. Source lookup agreement does not establish
clinical validity. External reference material is not accepted by this first
synthetic harness; adding it requires reviewed provenance and reuse terms.
