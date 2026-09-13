# Bounded custom-probe recovery

`record-run --probe-map mapping.json` enables an optional, conservative recovery
path. `replay-run` requires the same mapping file and verifies its checksum.
The original `analyze` and default web analysis retain their existing behavior.
No recovery is enabled automatically.

23andMe explains that internal identifiers can denote probes without a clear
rsID or changes without a known SNP identifier; an rsID cannot safely be invented
for every internal ID. See [23andMe's identifier documentation](https://customercare.23andme.com/hc/en-us/articles/212196908-What-Are-RS-Numbers-Rsid).
Its [reference/strand documentation](https://customercare.23andme.com/hc/en-us/articles/212883767-Which-Reference-Genome-and-Strand-Does-23andMe-Use)
does not establish the build of every file supplied to this application.

## Mapping and input contract

Only a declared `23andme-raw` product on GRCh37 or GRCh38, plus strand, is
supported. The input must identify 23andMe in its comment header (or explicitly
state `# Allelio product: 23andme-raw`) and declare the build in that header.
Conflicting/missing declarations remain unresolved. Filenames are never used to
infer product/build. Adding a header is an assertion that the context was checked,
not a way to convert coordinates between builds.
Build declarations are case-insensitive. Unsupported numeric builds still count
as conflicting evidence: a header containing both build 36 and build 38 cannot
authorize recovery. Explicit `Allelio product:` declarations must also agree.

The inspectable `allelio-probes/1` JSON format requires `source`, `version`,
`license`, `source_url`, `product`, `assembly`, `strand` and an `entries` list.
Each entry gives `probe`, `rsid`, `chromosome`, `position`, `ref` and `alt`.
See `examples/challenges/mapping.json` for an invented example.

Recovery requires a unique mapping, matching input coordinate and observed
alleles, and one unambiguous installed ClinVar allele identity for that rsID.
For a native-build mapping whose ClinVar allele is stored on the other build,
an optional `reference_anchor` must identify that same ClinVar `allele_id`,
chromosome and unchanged REF/ALT at its explicitly published reference position.
The native observation is not rewritten or lifted to another build. Both
placements are retained in the recovery evidence; conflicting source records,
changed alleles and strand flips remain unresolved.
Multiple locations/alleles at the mapped rsID remain unsupported in this first
path. No coordinate-only lookup, liftover, allele normalization, strand flip,
indel recovery or mitochondrial recovery is attempted. Palindromic SNP allele
pairs remain unresolved. Mapping/reference conflicts are explicit abstentions.

The parsed observation retains its original probe ID and genotype, mapping
source/version, recovered identity and decision reason. The existing duplicate
and conflicting-input rules apply after recovery. Coverage counts each input
row once; `probe_recovery_counts` separately records recovered, unresolved and
conflicting mapping decisions without adding them to total row counts.

## Availability and reuse

No production mapping is bundled or advertised as complete. The only shipped
mapping is deliberately synthetic and covered by this repository's MIT license.
A real mapping needs documented origin and redistribution permission/reuse terms
before it can be shipped; a nonempty license label alone is not legal verification.
User-supplied mappings are explicit local inputs and are never downloaded.
Successful synthetic recovery is a software check, not diagnostic validation.

### Verify native-build reference placements

The importer normally prefers GRCh38 records, even for a build-37 input. Use
the local preparation tool to pair explicitly published ClinVar placements:

```sh
python3 scripts/prepare_probe_reference.py sourced-mapping.json variant_summary.txt.gz \
  --output verified-probe-mapping
```

The input must already contain sourced probe-to-variant relationships with
native assembly, chromosome, coordinate and explicit assay alleles. An rsID-only
alias list is not an acceptable input. The tool checks the native placement,
selects the reference placement using the importer's GRCh38 preference, and
requires an unchanged chromosome/REF/ALT for the same AlleleID. It writes a
decision for every mapping row and hashes both input files. No mapping is
written when no rows pass. This verifies reference compatibility, not the
vendor alias itself or its reuse rights. It neither downloads reference data
nor establishes missing assay evidence from a coordinate match.

Use the resulting `mapping.json` with `record-run --probe-map`; replay requires
the exact same prepared mapping. The installed ClinVar records must still
match the prepared reference identity and AlleleID or recovery abstains.

### Production-source investigation (2026-09-13)

The reviewed public sources do not yet establish a redistributable mapping from
23andMe internal IDs to allele identities. 23andMe's identifier documentation
above explicitly allows internal IDs without a clear rsID. Its
[platform methods](https://permalinks.23andme.com/pdf/23_21-PRSMethodology_May2020.pdf)
describe custom content supplementing the underlying Illumina arrays, so a public
base-array manifest alone does not establish the identity of that custom content.
Illumina documents access to
[custom product files through the ordering MyIllumina account](https://knowledge.illumina.com/microarray/general/microarray-general-reference_material-list/000001531).
That access documentation does not establish redistribution permission for an
Allelio mapping. No production mapping has been imported from these sources.

A candidate must identify the exact supported product and reference build,
provide the internal-ID-to-rsID relationship and allele orientation with traceable
source evidence, and include terms permitting the intended reuse. Retain the
source version and checksum alongside any conversion. Validate its identities
against the installed reference and retain conflicts as unresolved. Do not fill
missing relationships by matching coordinates alone. Issue #28 remains open for
this data dependency; it does not require changes to the default recovery policy.
