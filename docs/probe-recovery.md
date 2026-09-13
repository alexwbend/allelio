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

A real, deliberately narrow mapping is available in
[`data/probe-mappings`](../data/probe-mappings/README.md): one documented F2 probe,
`i3002432` → `rs1799963`, for declared GRCh37 23andMe raw data. The FDA decision
summary establishes the alias and G20210A change; ClinVar establishes its explicit
reference placements. The mapping directory records provenance, source checksums,
reuse basis, preparation decisions and usage. It is never enabled automatically.
Other internal IDs remain unresolved unless a separately verified mapping is
explicitly supplied. The invented challenge mapping remains synthetic.

A new mapping still needs documented origin and reuse terms; a nonempty license
label alone is not verification. User-supplied maps are local inputs and never
downloaded. Successful recovery is a software check, not diagnostic validation.

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

Targeted searches for a specific probe uncovered the FDA's
[DEN160026 decision summary](https://www.accessdata.fda.gov/cdrh_docs/reviews/DEN160026.pdf),
page 1, explicitly linking `i3002432`, `rs1799963` and the F2 G20210A change.
The curated mapping above uses that primary evidence; it does not infer an alias
from coincident coordinates or copy a community alias list.

Broader candidates remain unsuitable for a complete mapping:

- Snappy's `data/iidaliases.json` contains rsID aliases, but its
  [third-party notice](https://github.com/zhaofengli/snappy/blob/2d5255f86352e1a048d13fa895fc9f991efb0d98/THIRDPARTY.md)
  assigns the SNPedia data noncommercial share-alike terms separately from its
  code license. The alias file also lacks explicit build and assay alleles.
- Public base-array manifests do not define all vendor custom content. The
  [vendor methods](https://permalinks.23andme.com/pdf/23_21-PRSMethodology_May2020.pdf)
  describe that added content; Illumina's
  [ordering-account access documentation](https://knowledge.illumina.com/microarray/general/microarray-general-reference_material-list/000001531)
  does not grant redistribution rights for a vendor custom manifest.
- Public paired array/sequencing research datasets can test concordance, but a
  matching observed genotype alone does not establish a complete assay definition.
  No participant data or empirically inferred mappings are included here.

Expand this collection only when each added relationship has equivalent explicit
identity, allele, build and reuse evidence. Keep conflicts and unsupported contexts
unresolved. Bounded coverage is intentional; it is not a claim that all internal
IDs can be resolved.
