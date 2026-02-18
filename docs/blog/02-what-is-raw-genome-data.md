# What Is Raw Genome Data? A Plain-English Guide to the File Your DNA Test Gave You

You took a DNA test. Maybe it was 23andMe, AncestryDNA, or MyHeritage. You got your ancestry results, maybe some health reports, and then you noticed something buried in your account settings: an option to download your "raw data."

That file — usually a few megabytes of text — is one of the most personal files you'll ever own. It contains hundreds of thousands of data points about your DNA. But what exactly is in it, and what can you do with it?

## Your Genome, Summarized

Your complete genome contains about 3.2 billion base pairs — the individual "letters" (A, T, C, G) that make up your DNA. If you printed it out, it would fill roughly 1.5 million pages of text.

Consumer DNA tests don't read your entire genome. That would be whole genome sequencing, which is a different (and more expensive) process. Instead, companies like 23andMe and AncestryDNA use a technology called genotyping microarrays, sometimes called "SNP chips."

A genotyping chip tests specific positions in your genome that are known to vary between people. These positions are called Single Nucleotide Polymorphisms, or SNPs (pronounced "snips"). A typical consumer genotyping chip tests between 600,000 and 900,000 SNPs — a tiny fraction of your total genome, but enough to reveal a tremendous amount of information about your ancestry, traits, and health-related genetic variants.

## What's Inside the Raw Data File

When you download your raw data, you get a plain text file. The format varies by company, but the information is essentially the same. Each line represents one SNP and contains four pieces of information.

First is the **rsID** — a unique identifier for that specific position in the genome. It looks like "rs429358" or "rs7412." These identifiers are standardized across the scientific community, which means researchers worldwide use the same names for the same positions.

Second is the **chromosome** — which of your 23 chromosome pairs the SNP sits on. This is a number from 1 to 22, or X or Y for the sex chromosomes.

Third is the **position** — the exact numerical location on that chromosome.

Fourth is the **genotype** — the two letters you carry at that position, one inherited from each parent. For example, "AG" means you have an A on one copy of the chromosome and a G on the other. "AA" means both copies carry an A.

A typical raw data file has about 600,000 to 700,000 of these lines. Here's what a few lines from a 23andMe file look like:

```
# rsid    chromosome    position    genotype
rs4477212    1    82154    AA
rs3094315    1    752566    AG
rs3131972    1    752721    GG
```

That's it. No names, no health reports, no ancestry percentages. Just hundreds of thousands of rows of variant identifiers and the letters you carry.

## Why This File Matters

That modest text file is remarkably powerful. Each of those SNPs has been studied by scientists around the world. Some are associated with eye color or hair texture. Some influence how you respond to certain medications. Some are linked to increased or decreased risk for conditions like heart disease, diabetes, or cancer.

By itself, the raw file is just data. But when you cross-reference it against scientific databases — which is exactly what Allelio does — patterns emerge. You can see which of your variants have been studied, what the research says, and how the medical genetics community has classified them.

This is also why the file is so sensitive. It contains information about your health risks, your ancestry, your family relationships, and even your predisposition to certain psychological traits. Unlike a password, you can't change your genome if it's compromised.

## The Different File Formats

The three most common raw data formats are:

**23andMe** files are tab-separated text files. Lines starting with "#" are comments (metadata about the file). Data lines have four columns: rsID, chromosome, position, and genotype. No-call positions (where the chip couldn't determine your genotype) are marked with "--".

**AncestryDNA** files are also tab-separated, but they split the genotype into two separate columns (allele1 and allele2) and include a header row with column names. No-calls appear as "0" values.

**VCF (Variant Call Format)** is the standard format used by clinical and research sequencing. VCF files are more complex, with extensive metadata headers (lines starting with "##"), a column header line (starting with "#CHROM"), and data lines that encode genotypes differently — using numbers like "0/1" to indicate which alleles you carry relative to the reference genome. VCF files can come from whole genome sequencing, exome sequencing, or some direct-to-consumer tests.

Allelio can parse all three formats automatically. You upload the file, and the parser detects the format, extracts the variants, filters out no-calls, and passes them along for analysis.

## What You Can Do With Your Raw Data

Having your raw data gives you independence from any single company's interpretation. The companies that genotyped your DNA provide their own reports, but those reports are limited by what the company chooses to cover and how they choose to present it.

With your raw file, you can use tools like Allelio to explore your variants against up-to-date scientific databases, get AI-powered explanations in plain language, and generate detailed reports — all without sending your data to anyone.

You can also use it to explore your pharmacogenomics profile (how your genetics might affect drug metabolism), investigate carrier status for inherited conditions, or simply satisfy your curiosity about what makes you genetically unique.

## A Word About Privacy

Your raw genome data is arguably the most personal data you possess. It doesn't just describe you — it reveals information about your biological relatives, your ancestry, and your predispositions. It can never be made anonymous (a genome is, by definition, unique to you), and it can never be changed.

This is exactly why Allelio was built to work entirely on your local computer. Your genotype file is never uploaded to a server. The analysis happens on your machine, using databases stored locally. The AI that generates explanations runs on your hardware through Ollama. Nothing leaves your computer.

If you choose to use other tools with your raw data, be thoughtful about where you upload it and what privacy guarantees the service offers. Once genetic data is shared, it cannot be un-shared.

---

*Allelio is for educational purposes only and is not a substitute for medical advice. Learn more at [allelio.org].*
