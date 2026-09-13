# Curated custom-probe mapping, version 2026-09-13.1

`23andme-grch37-f2-v1.json` is an optional mapping for **one** real probe:
`i3002432` → `rs1799963`, F2 G20210A, genomic plus-strand G>A.
It supports explicitly declared 23andMe raw-data inputs on GRCh37, chromosome 11,
position 46761055. It does not claim coverage of other internal IDs, every chip
revision, or a person's complete genotype. Unknown probes remain unresolved.
The installed reference must match ClinVar AlleleID 28349, GRCh38 chromosome 11,
position 46739505, G>A. No coordinate conversion is applied to the input.

`23andme-grch37-f2-gba1-v1.json` is the next conservative catalogue revision.
It retains that F2 entry and adds `i4000415` → `rs76763715`, GBA1 N370S,
GRCh37 chromosome 1 position 155205634 T>C, anchored to ClinVar AlleleID 19329
at GRCh38 position 155235843 T>C. The FDA decision identifies N370S with the
rsID; the vendor report identifies the same named variant with the internal
marker, alleles, positive strand and build 37. ClinVar supplies paired placements
for the same AlleleID. A different T>G allele sharing the rsID is not admitted.

## Evidence chain

1. The FDA's [DEN160026 decision summary](https://www.accessdata.fda.gov/cdrh_docs/reviews/DEN160026.pdf),
   corrected November 2, 2017, page 1, explicitly identifies the tested F2 G20210A
   change with both `rs1799963` and `i3002432`. This establishes the alias and
   specific assayed change independently of any coordinate lookup.
   The same decision identifies GBA1 N370S as `rs76763715`.
2. The manufacturer's [illustrative sample report](https://medical.23andme.com/wp-content/uploads/2023/02/Jamie-Hereditary-Thrombophilia-2-variants-F5-and-F2-sample-report-1.pdf),
   page 2, corroborates the marker and distinguishes typical G from variant A.
   This is an illustrative vendor report, not an individual research participant.
   Its [Parkinson's illustrative report](https://medical.23andme.com/wp-content/uploads/2017/09/Parkinson_one_N370S_nocall_G2019S.pdf)
   names N370S marker `i4000415`, typical T and variant C, and states positive
   strand/build 37. Together with the FDA's N370S rsID, this establishes the
   second alias and assay context without a coordinate-derived alias.
3. [ClinVar variation 13310](https://www.ncbi.nlm.nih.gov/clinvar/variation/13310/)
   publishes the explicit GRCh37 and GRCh38 G>A placements. The mapping was
   prepared against the complete 2026-09-06 variant-summary extract, requiring
   the same AlleleID, chromosome and alleles at both placements. Its checksum and
   the preparation decision are recorded in the accompanying JSON files.
4. The [vendor's strand documentation](https://customercare.23andme.com/hc/en-us/articles/212883767-Which-Reference-Genome-and-Strand-Does-23andMe-Use)
   describes the raw-data convention. The input file must still declare supported
   product/build context; the mapping never supplies a missing input declaration.

The FDA document SHA-256 is
`75d13a55ece6f130684cf3a5654229d6a3ea8e476e85c7ffff2f81fea29c2591`.
The complete ClinVar source SHA-256 is
`0946d1661f102f39e4a5b37db1e04be2990478eb547cceb21ffb0ba23c7ee78f`.
The vendor PDF was inspected through the web reader; no byte-level fingerprint
is claimed for that corroborating source. All sources were reviewed September
13, 2026. Source documents are linked, not redistributed here.

## Availability and reuse

The JSON curation and documentation are supplied under Allelio's MIT license.
They contain factual identifiers, nucleotide identities, coordinates, citations
and original provenance metadata, rather than copied report prose, images or a
third-party alias database. The [FDA website policy](https://www.fda.gov/about-fda/about-website/website-policies)
permits reuse of its public-domain content unless otherwise noted; the cited
agency decision supplies the alias fact. The [U.S. Copyright Office](https://www.copyright.gov/engage/writers/)
distinguishes facts from protected expression. Reference sequence/placement data
are used consistently with [NCBI's data policies](https://www.ncbi.nlm.nih.gov/home/about/policies/).
This does not relicense the manufacturer's report or imply FDA or vendor
endorsement of Allelio. No SNPedia-derived alias list or participant genotype
was used to construct this mapping.

## Use and reproduction

From a source checkout, use the prepared file explicitly:

```sh
allelio record-run input.txt --database ~/.allelio/data/allelio.db \
  --manifest run.json --evidence-output evidence.json \
  --probe-map data/probe-mappings/23andme-grch37-f2-gba1-v1.json
```

For a package installation, download the prepared JSON from this repository and
pass its local path. Replay requires the exact same mapping file. No map is
selected or downloaded automatically; `analyze` and web defaults are unchanged.
The `.source.json` file is the curation input, not the prepared cross-build map.
To reproduce the prepared map using the checksummed ClinVar extract:

```sh
python3 scripts/prepare_probe_reference.py \
  data/probe-mappings/23andme-grch37-f2-v1.source.json variant_summary.txt.gz \
  --output reproduced-f2
```

`reproduced-f2/mapping.json` and `verification.json` should match the prepared
JSON and `.verification.json` respectively. A newer reference is a new validation
run, not an interchangeable replacement for the recorded source.

Recovery establishes a supported identifier relationship. It does not validate
an individual's assay call, provide a diagnosis, or extend the FDA's assessment
of 23andMe's test to Allelio. All existing input-conflict, allele, reference and
replay checks still apply.
