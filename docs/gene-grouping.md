# Findings by gene

Allelio now organizes returned findings by gene in the CLI, web page, and both
HTML exports. Expand a gene to inspect the findings it contains. The individual
annotations and ranking are unchanged; grouping adds no combined risk score.

Counts refer to returned findings, not every variant in the gene or every site
on the uploaded array. They are computed before display limits and category
filters. The CLI top-results table keeps its requested limit, followed by a
summary of every returned gene group. Web category filters show visible versus
total group counts. HTML exports retain all findings so every summary link has
a detail target. Large analyses therefore produce larger exports than earlier
releases that truncated the result list. No gene grouping implies that a gene was comprehensively tested.

## Gene identity and shared findings

Associations are gathered from ClinVar, GWAS, and ClinPGx. Semicolon/comma lists
and spaced intergenic separators are split, while hyphenated symbols such as
HLA-DQA1 stay intact. The source's HGNC identifier is used only when its mapping
to a symbol is unambiguous. Known source aliases sharing an ID can be grouped;
no broad symbol-alias inference is performed. Missing IDs use symbol groups.
Conflicting source IDs are not forced together. Unassigned findings remain
visible in an explicit group.

Within a group, matching rsID, chromosome, position, genotype, matched allele,
and category identify duplicate results. Conflicting genotypes/categories remain
separate. Findings associated with several genes appear in each relevant group;
group counts therefore must not be summed into a genome-wide count. Grouping
expresses source associations, not a new causal gene assignment.

## Function descriptions

A small offline catalogue provides original, short paraphrases of the Normal
Function sections of MedlinePlus Genetics for BRCA1, BRCA2, CFTR, APOE and HFE.
Each description links its source and records catalogue version 2026-09-12:

- https://medlineplus.gov/genetics/gene/brca1/
- https://medlineplus.gov/genetics/gene/brca2/
- https://medlineplus.gov/genetics/gene/cftr/
- https://medlineplus.gov/genetics/gene/apoe/
- https://medlineplus.gov/genetics/gene/hfe/

Other genes explicitly state that a sourced function summary is unavailable.
No network request or AI call fills missing descriptions. Future catalogue
updates should cite sources and change the version deliberately.

The combined note explains that several findings alone do not establish higher
risk, a haplotype, or compound heterozygosity. Determining those relationships
requires evidence outside this presentation feature.

## Saved results and reproducibility

New web payloads preserve gene assignments and groups with indices into their
canonical results array. Older saves without grouping metadata keep their flat
web view; exporting them can still group their recorded gene symbols. Exports
recompute summaries from their findings rather than trusting submitted counts
or source URLs. Corrupt grouping metadata cannot hide unlisted web findings.

Tests cover counts, overlapping genes, ambiguous identifiers, missing genes,
source links, HTML escaping, findings beyond old export limits, CLI top limits,
and the actual browser rendering code with category filters.

## HTML presentation

Both standalone exports share an offline system-font stack, lavender-gray
surfaces, thin rounded panel borders, and restrained mint/cyan accents. Clinical
status labels keep their existing meanings and warning colors. No remote fonts
or branding assets are fetched. Tables can scroll on small screens.
