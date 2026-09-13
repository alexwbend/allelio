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

The inspectable `allelio-probes/1` JSON format requires `source`, `version`,
`license`, `source_url`, `product`, `assembly`, `strand` and an `entries` list.
Each entry gives `probe`, `rsid`, `chromosome`, `position`, `ref` and `alt`.
See `examples/challenges/mapping.json` for an invented example.

Recovery requires a unique mapping, matching input coordinate and observed
alleles, and one unambiguous installed ClinVar allele identity for that rsID.
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
