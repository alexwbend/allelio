# VCF parsing evidence

VCF records returned by `parse_vcf()` carry an optional `Variant.vcf_evidence`
object. Existing four-argument `Variant` construction remains supported and
consumer-array records leave this object unset.

The evidence retains REF, ordered ALT entries, GT allele indices and ordered
allele sequences, ploidy, within-record phase, PS, QUAL, FILTER, GQ, DP, and the
raw `##reference` declaration. Missing fields are `None`; numerical zero remains
a source value. Quality fields are preserved as strings, not interpreted as a
validation score. No reference URL is fetched or used to infer a verified build.

The legacy genotype display sorts diploid alleles. Use evidence allele order
when inspecting phase. Haploid SNVs retain a single allele, allowing the existing
zygosity calculation to distinguish one copy from two. A phase delimiter alone
does not establish phase relationships between different records.

## Current limits

The parser selects the first sample. Missing/partial GT calls, unsupported
ploidy, and records without identifiers are still skipped. Evidence preservation
does not add coordinate lookup, reference normalization, cross-build matching,
quality filtering, or general indel/structural-variant interpretation. ClinVar SNP matching uses explicit VCF alleles and indices, requires the same
reference allele and a declared target alternate, and never complements a VCF
call to force a match. Multiallelic SNPs can carry two different alternates;
each annotated alternate is counted independently. Non-SNP records and
reference mismatches have unknown ClinVar zygosity. This is allele compatibility,
not verification that the source and input coordinates/builds match.

GWAS and pharmacogenomic matching still use the legacy SNP path. Non-SNP VCF
records are withheld from that path so flattened sequences cannot look like SNP
genotypes; no new GWAS/PGx interpretation is claimed here. Haploid multibase alleles use `--` in the legacy display to avoid being read as
two SNP alleles. Full source alleles remain available in the evidence object.

## Reproducible development checks

Run `python3 -m pytest tests/test_vcf_evidence.py tests/test_vcf_ploidy.py -q`.
The tests generate synthetic records, including ordered multiallelic indels,
phased/unphased calls, haploid SNVs, missing fields, and gzip input.

`python3 scripts/publication_baseline.py --output /tmp/allelio-baseline.json`
combines the shipped example checks, lexical-filter fixture counts, and four
VCF ploidy challenges. It needs a source checkout with the development dependencies.
It uses shipped fixtures and temporary storage, not personal genomic inputs or
live reference downloads. Its results are development evidence, not independent
validation or a clinical accuracy estimate. Review generated artifacts before
sharing: source hashes and checkout revision are included for reproducibility.

Source format: [VCF specification](https://samtools.github.io/hts-specs/VCFv4.3.pdf).
