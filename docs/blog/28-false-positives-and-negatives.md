# False Positives and False Negatives: Why Consumer DNA Results Aren't Always Right

You've downloaded your raw DNA file from 23andMe or AncestryDNA and uploaded it to Allelio for analysis. A variant appears in your results that concerns you—maybe it's linked to a serious disease, or maybe it contradicts something you thought you knew about your health. Your first instinct might be panic. But before you do, consider this: what if the result is wrong?

DNA testing, including Allelio's analysis, isn't perfect. It can produce false positives (saying you have a variant you actually don't) and false negatives (missing variants you actually do have). Understanding how and why these errors happen helps you interpret your results with appropriate skepticism—and confidence in the ones that are likely correct.

## What Are Genotyping Errors?

When a DNA testing company processes your sample, they're reading your genetic code using a technology called SNP genotyping. The process is impressively accurate but imperfect.

A SNP (single nucleotide polymorphism) is a spot in your DNA where people commonly have different letters—for example, some people have an A and others have a G at a particular position. The genotyping chip used by consumer companies can determine which letter you have at roughly one million of these positions.

But here's the thing: the chip is making a judgment call based on signals. It's like reading a fuzzy photocopy of your genetic code and trying to figure out what each letter says. Most of the time, the signal is clear. Sometimes, it's ambiguous.

## Typical Error Rates

Consumer DNA tests have error rates around **0.1 to 0.5%** for common variants—variants seen frequently in the population. This sounds small, but it's important to understand what it means in practice.

If you have 1 million variants tested (a typical SNP chip), you have:
- 1,000 to 5,000 potential errors
- Some of those errors are false positives (called as present when absent)
- Some are false negatives (missed entirely)

For most of those variants, errors don't matter—they're variants that don't affect health, and whether they're called correctly or not has no consequence.

But if you're looking at health-related variants, a small error rate can be significant, especially for:

**Rare Variants**: Variants that appear in less than 1% of the population often have higher error rates than common ones. The chip's algorithms are trained on common variants, so rare variants are handled less reliably. If you carry a rare variant associated with disease, the error rate might be 5% or more.

**Boundary Cases**: Sometimes a variant sits in a region where the signal is ambiguous—maybe there's a technical artifact, or DNA quality issues, or the two alleles (copies) you inherited are similar enough to confuse the machine.

## Why Errors Happen: Five Common Causes

**1. DNA Quality Issues**

Not all DNA samples are perfect. If the DNA in your sample was degraded, contaminated, or of low quality, the genotyping is more error-prone. Poor DNA quality can lead to misreads.

**2. Batch Effects**

DNA samples are processed in batches. Sometimes, technical issues during a particular batch (temperature variations, reagent problems, timing) can affect genotyping accuracy across all samples in that batch. A variant that's called correctly in one batch might be misread in another.

**3. Insufficient Read Depth**

Genotyping works by looking at many copies of your DNA at each position. If there aren't enough copies (low read depth), the machine has less evidence and might misread a variant.

**4. Nearby Sequence Complexity**

Some regions of the genome are inherently harder to read. If a SNP sits next to repeating sequences or complex DNA structure, the machine might struggle to accurately call the base pair.

**5. Allele-Specific Biases**

Sometimes the chip performs better or worse at detecting one specific allele (letter) than another. A variant might be called correctly in people with genotype AA but misread in people with genotype AG, leading to systematic biases.

## No-Calls and Why "I Don't Know" Is Better Than Wrong

Sometimes the genotyping machine encounters a spot where the signal is too ambiguous to make a call. Rather than guess, it returns a "no-call"—essentially saying, "I can't confidently determine what you have here."

A no-call might feel frustrating, but it's actually a sign of good quality control. The machine is saying, "rather than give you wrong information, I'm telling you I don't know." This is better than a false positive or false negative.

If Allelio shows that a variant has a "no-call" for you, it means the original test couldn't determine your status. If that variant is important for your health, you might want to seek clinical-grade sequencing (whole genome sequencing or targeted sequencing) that can confidently call that position.

## Clinical Confirmation: The Gold Standard

Here's where clinical genetics comes in. If Allelio's analysis reveals a variant that could significantly affect your health, the standard practice is to confirm it with clinical-grade sequencing. This usually means a test ordered by your doctor and performed at a clinical laboratory using different technology (like Sanger sequencing or whole genome sequencing).

Clinical sequencing is more expensive but more accurate. It uses different methods to read the DNA, providing independent verification. If both consumer genotyping and clinical sequencing agree you carry a variant, you can be confident. If they disagree, the clinical result is more trustworthy.

## False Positives in Analysis

Even if your genotype is correct, errors can occur during analysis. Allelio uses the ClinVar database, which contains classifications of variants (benign, likely benign, uncertain, likely pathogenic, pathogenic). But these classifications themselves can be wrong.

A variant might be classified as pathogenic in ClinVar based on limited evidence—maybe only one or two published studies suggested it causes disease. Years later, larger studies show it doesn't actually cause disease. But the database hasn't been updated.

Or the opposite: new evidence emerges that a benign variant actually does increase disease risk. The database is constantly being updated, but there's always a lag.

Allelio helps by reporting evidence for each classification, including when there's disagreement or uncertainty. If a variant's significance is disputed, you'll see that reflected in the analysis.

## False Negatives: What You Don't See

False negatives—variants you actually carry but aren't detected—are harder to think about because they're absence. You don't see them, so how do you know they're there?

Consumer SNP chips look at roughly one million known positions. They miss:

- **Novel variants**: Variants unique to you or your family that haven't been catalogued in databases
- **Structural variants**: Large chunks of DNA deleted, duplicated, or inverted—these SNP chips often can't detect
- **Deep intronic variants**: Variants in the parts of genes that don't code for protein—these are usually not well-covered by SNP chips
- **Rare variants**: Variants so uncommon they might not be well-represented on the chip

If you have a disease running in your family but Allelio doesn't show a known genetic cause, that doesn't mean there isn't a genetic component. It might mean the causal variant isn't something the SNP chip detects. It might be a variant that hasn't been discovered yet.

This is why Allelio results should never be used as a definitive "you don't have a genetic predisposition to X" statement. They show what's detectable with the tools available. They don't show everything.

## What to Do If You Find Something Concerning

If Allelio's analysis reveals a variant that concerns you:

**1. Research Thoroughly**: Look at the evidence. Is the variant classified as definitely pathogenic, or just possibly harmful? What does the literature say?

**2. Consider Your Ancestry**: As discussed in our earlier post about the diversity gap, variant classifications might be more reliable if you're of European ancestry. Less so otherwise.

**3. Talk to a Genetic Counselor or Doctor**: Don't panic, but do seek professional guidance. A genetic counselor can help you interpret results in the context of your family history and health.

**4. Consider Clinical Confirmation**: If the variant could significantly affect your health, ask your doctor about clinical-grade sequencing to confirm the finding.

**5. Get Appropriate Screening or Monitoring**: Even with false positives, if a variant increases cancer risk, for example, the appropriate response might be increased screening—which is helpful regardless of whether the variant's effect is exactly as stated in the database.

## The Bigger Picture

Genomic data is complex, and the tools for analyzing it—Allelio included—are powerful but imperfect. Error rates matter, but they shouldn't paralyze you with fear or false confidence. They should inform thoughtful interpretation.

When Allelio shows you a variant, ask yourself: Is this common or rare? Is the clinical significance certain or uncertain? Does it align with my family history? If the answer to the last question is yes, and the first two suggest it's reliable, the result is probably meaningful.

When Allelio doesn't show something, remember that absence of evidence isn't evidence of absence. It means that particular analysis tool couldn't detect it—not that it doesn't exist.

Your raw DNA data is valuable. Allelio helps you understand it. But like all tools, it works best when you understand its limitations and use its results as a starting point for conversation with healthcare providers who know you and your health history.

---

*Allelio is for educational purposes only and is not a substitute for medical advice. Learn more at [allelio.org].*
