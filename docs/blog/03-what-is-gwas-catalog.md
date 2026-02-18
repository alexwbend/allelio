# What Is the GWAS Catalog? How Scientists Map Genes to Traits and Diseases

When scientists announce that they've found a gene "linked to" heart disease, depression, or height, that finding almost always comes from a specific type of study called a Genome-Wide Association Study — or GWAS. And the world's most comprehensive collection of those findings lives in a single, freely accessible database: the GWAS Catalog.

Allelio uses the GWAS Catalog as one of its two primary data sources. Here's what it is, how it works, and why it matters for understanding your genome.

## The Problem GWAS Was Built to Solve

For most of human history, genetics focused on conditions caused by a single gene. Diseases like cystic fibrosis, sickle cell anemia, and Huntington's disease follow clear inheritance patterns — one faulty gene, one condition. These are called Mendelian diseases, and they're relatively straightforward to study.

But most human traits and diseases don't work that way. Height, blood pressure, diabetes risk, intelligence, susceptibility to depression — these are influenced by hundreds or thousands of genetic variants, each contributing a tiny effect. To find those tiny effects, scientists needed a new approach. That approach is GWAS.

## How a GWAS Works

A Genome-Wide Association Study works by comparing the genomes of thousands (sometimes hundreds of thousands) of people. Researchers divide participants into groups — for example, people with Type 2 diabetes and people without it — and then scan their genomes to find SNPs that are statistically more common in one group than the other.

The "genome-wide" part is key. Rather than testing a specific gene that researchers suspect might be involved, GWAS tests hundreds of thousands or millions of SNPs simultaneously. This hypothesis-free approach has led to discoveries that nobody predicted.

Each SNP is tested individually, and the result is a p-value — a statistical measure of how likely the observed difference is to have occurred by chance. Because so many tests are run simultaneously, the threshold for significance is extremely strict: a p-value must be below 5 x 10^-8 (that's 0.00000005) to be considered "genome-wide significant."

Some GWAS also report an odds ratio, which describes the size of the effect. An odds ratio of 1.2 means the variant is associated with a 20% increase in risk compared to the reference allele. Most GWAS-identified variants have modest effect sizes, typically between 1.05 and 1.5.

## What the GWAS Catalog Contains

The GWAS Catalog is maintained by the European Bioinformatics Institute (EMBL-EBI) in collaboration with the National Human Genome Research Institute (NHGRI), part of the U.S. National Institutes of Health. It was established in 2008 and is continuously updated.

The catalog is a curated collection of all published GWAS that meet certain quality criteria. For each study, the catalog records the SNPs that reached genome-wide significance, along with the associated trait or disease, the p-value, the odds ratio (when available), the mapped gene(s), the study's PubMed reference, and the populations studied.

As of 2025, the GWAS Catalog contains data from over 6,500 publications, covering more than 500,000 variant-trait associations across thousands of traits and conditions. It is the single most comprehensive resource for understanding the genetics of complex traits.

## GWAS vs. ClinVar: Different but Complementary

If you've read our article about ClinVar, you might wonder how the GWAS Catalog differs. The distinction is important.

ClinVar focuses on **clinical significance** — variants that clinical laboratories have evaluated in the context of medical diagnosis. It answers the question: "Has this variant been classified as pathogenic, benign, or somewhere in between?"

The GWAS Catalog focuses on **statistical associations** — variants that have been found to occur more or less frequently in people with a particular trait or condition. It answers the question: "Is this variant more common in people with diabetes than in people without diabetes?"

These are fundamentally different kinds of evidence. A ClinVar "pathogenic" classification for a BRCA1 variant means that variant has been evaluated by clinical experts and found to substantially increase cancer risk. A GWAS association between a SNP near a gene and Type 2 diabetes means that, statistically, across a large population, people with that SNP variant had a slightly different rate of diabetes.

Allelio uses both databases because together they give a more complete picture. ClinVar catches the high-impact, well-characterized clinical variants. The GWAS Catalog fills in the vast landscape of smaller-effect associations that contribute to complex traits and conditions.

## The Limitations You Should Know About

GWAS findings are powerful, but they come with important caveats.

**Association is not causation.** A GWAS finding means a SNP is statistically correlated with a trait in the studied population. It doesn't prove the SNP causes the trait. The actual causal variant might be nearby on the chromosome and simply inherited together (this is called linkage disequilibrium).

**Effect sizes are usually small.** Most GWAS variants increase risk by only 5-50%. For any individual, the effect of a single variant is typically negligible. It's the cumulative effect of many variants — combined with environment and lifestyle — that shapes your actual risk.

**Population matters.** The vast majority of GWAS have been conducted in people of European ancestry. Findings may not generalize well to other populations. A variant that's associated with a trait in Europeans may not show the same association in East Asian, African, or South American populations, and vice versa. This is a well-known gap in genomics research.

**The study is only as good as its design.** Sample size, phenotype definition, statistical methods, and replication all affect the reliability of GWAS findings. The GWAS Catalog includes study metadata so you can assess quality, but interpreting this requires some expertise.

## How Allelio Uses the GWAS Catalog

When you analyze your genome with Allelio, the tool cross-references your variants against a local copy of the GWAS Catalog. For each match, it shows you the associated trait, the p-value, the odds ratio (if available), the mapped gene, and a link to the published study.

This means you can see which of your variants have been the subject of published research and what those studies found. Some people discover variants associated with coffee consumption, sleep patterns, or educational attainment. Others find associations with conditions like coronary artery disease, asthma, or Alzheimer's risk.

As with everything in Allelio, these findings are for education only. A GWAS association with a p-value of 10^-12 is a robust statistical finding — but it doesn't tell you what will happen to you personally.

## The Bigger Picture

The GWAS Catalog represents one of the great achievements of modern genomics. In less than two decades, genome-wide association studies have identified thousands of genetic loci involved in human traits and diseases, fundamentally transforming our understanding of human biology.

But we're still in the early chapters. Most of the heritability of complex traits remains unexplained — a puzzle known as "missing heritability." Future research, larger studies, and greater diversity in study populations will continue to fill in the picture.

In the meantime, tools like Allelio give you a window into what's known today. And the GWAS Catalog is one of the best windows we have.

---

*Allelio is for educational purposes only and is not a substitute for medical advice. Learn more at [allelio.org].*
