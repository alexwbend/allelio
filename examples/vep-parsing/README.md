# Invented VEP parsing cases

These are constructed software inputs, not observed human genotypes or clinical
reference labels. Coordinates lie within the upstream VEP test cache's chromosome
21 region. Identifiers are invented rsID-shaped labels; no biological identity
or genotype truth is asserted. All files and the invented reference object are MIT.

Six cases (seven rows) satisfy the initial shared parsing contract: diploid
heterozygous, alternate, reference, haploid, phased, and a two-record input.
Five cases deliberately fall outside the adapter's shared scope: missing build,
failed filter, no call, indel and multiallelic input. That exclusion describes
the adapter, not whether VEP supports those representations. VEP must still
execute successfully for every recorded case; failures cannot be exclusions.

The Allelio database has one invented, off-input record to satisfy initialization;
no input has a matching annotation. This isolates input handling. No consequence,
genotype interpretation, allele matching, source selection, report usefulness or
clinical accuracy is scored. These are internal development fixtures, not unseen
or independently curated validation. Retain their first execution result.
