# What Is ClinVar? The Free Database Connecting Your DNA Variants to Medical Research

If you've ever spit into a tube for 23andMe or AncestryDNA and wondered what your raw data actually means, you've probably come across the word "ClinVar." It sounds technical, and it is — but the idea behind it is surprisingly simple. ClinVar is the world's largest free, public database that links specific genetic variants to known medical conditions. And it's one of the core databases that Allelio uses to help you understand your genome.

Let's break it down.

## DNA Variants: The Starting Point

Your genome is made up of roughly 3 billion base pairs — the A, T, C, and G "letters" that encode everything from your eye color to how you metabolize caffeine. The vast majority of those letters are identical from person to person. But scattered across your genome are millions of small differences called variants.

The most common type of variant is a Single Nucleotide Polymorphism, or SNP (pronounced "snip"). A SNP is a single-letter change at a specific location in the genome. For example, at a position where most people have the letter C, you might have a T.

Most SNPs are harmless. Some are associated with traits like earwax type or asparagus smell detection. But a small number have been linked to medically significant conditions — and that's where ClinVar comes in.

## What ClinVar Actually Is

ClinVar is a public archive maintained by the National Center for Biotechnology Information (NCBI), which is part of the U.S. National Institutes of Health (NIH). It was launched in 2013 and has grown steadily ever since.

At its core, ClinVar is a collection of submissions. Clinical laboratories, research institutions, genetic testing companies, and expert panels submit reports that describe the relationship between a specific genetic variant and a medical condition. Each submission includes the variant's identifier (usually an "rs" number like rs429358), the condition it's associated with, and a classification of how significant that association is.

Those classifications follow a standardized five-tier system established by the American College of Medical Genetics and Genomics (ACMG):

**Pathogenic** means the variant is considered to cause or strongly contribute to disease. **Likely pathogenic** means there's strong but not definitive evidence. **Uncertain significance** means there isn't enough evidence yet to classify it either way. **Likely benign** means the variant is probably harmless. And **benign** means it's considered harmless.

## Why Multiple Opinions Matter

One of the most important things to understand about ClinVar is that it's a collection of opinions, not a single source of truth. Different laboratories can submit different classifications for the same variant. One lab might call a variant "pathogenic" while another calls it "uncertain significance."

This isn't a flaw — it's a feature. Genetic science is evolving rapidly. New evidence can change how a variant is understood. ClinVar captures this complexity by showing all submissions, their dates, the submitting organization, and a "review status" that indicates how much expert consensus exists.

A variant with a "practice guideline" or "reviewed by expert panel" status has the strongest evidence behind its classification. A variant with a single submitter has less. When Allelio shows you ClinVar results, the review status is one of the most important things to pay attention to.

## What ClinVar Contains

As of early 2025, ClinVar contained over 2.5 million submitted records covering more than 1.3 million unique variants. It covers a wide range of conditions, from hereditary cancers (BRCA1, BRCA2) and cardiac conditions (hypertrophic cardiomyopathy) to metabolic disorders (phenylketonuria) and neurological conditions (Alzheimer's risk via APOE).

ClinVar is particularly strong in areas where clinical genetic testing is well-established, such as hereditary cancer syndromes and rare Mendelian diseases (conditions caused by a single gene). It is less comprehensive for complex, multifactorial conditions where hundreds of small-effect variants contribute.

## What ClinVar Doesn't Tell You

ClinVar is a powerful resource, but it has real limitations. A variant being listed in ClinVar as "pathogenic" does not mean you have or will develop that condition. Many pathogenic variants have incomplete penetrance, meaning only a fraction of people who carry them ever develop symptoms. Your environment, lifestyle, other genetic variants, and plain chance all play a role.

Similarly, a variant being absent from ClinVar doesn't mean it's harmless. It may simply be unstudied. The database is continuously growing, but it represents only a fraction of all possible human genetic variation.

ClinVar also reflects the demographics of genetic research. Most submissions come from studies of people with European ancestry. This means classification accuracy may be lower for individuals from underrepresented populations, and some variants common in those populations may be missing entirely.

## How Allelio Uses ClinVar

When you upload your raw genotype file to Allelio, the tool looks up each of your variants in a local copy of ClinVar stored on your computer. For every match it finds, it shows you the gene, the clinical significance classification, the associated conditions, and the review status.

Allelio ranks findings by clinical significance — pathogenic variants appear first, followed by likely pathogenic, risk factors, and so on. This helps you focus on the most potentially meaningful results.

Importantly, all of this happens locally. Your genetic data never leaves your machine. The ClinVar database is downloaded once during setup and stored in a SQLite database on your computer.

## The Bottom Line

ClinVar is one of the most important resources in modern genetics. It's free, it's public, and it's growing every day. But it's a research tool, not a crystal ball. The classifications it contains are the current best understanding of the scientific community, and that understanding changes over time.

If ClinVar — or Allelio — flags something in your results that concerns you, the right next step is always the same: talk to a genetic counselor or healthcare provider who can put the finding in the context of your full medical picture.

---

*Allelio is for educational purposes only and is not a substitute for medical advice. Learn more at [allelio.org].*
