# What Does Clinical Significance Mean? How Scientists Decide If a DNA Variant Matters

You're looking at your Allelio results and you see a variant labeled "pathogenic" or "likely pathogenic" or "uncertain significance." But how did anyone decide that? How do scientists determine whether a genetic variant actually matters for human health? This process is called **clinical significance classification**, and understanding it will help you interpret genetic information much more wisely.

## The ACMG 5-Tier Classification System

The gold standard for classifying genetic variants comes from the American College of Medical Genetics and Genomics (ACMG). They created a 5-tier system that most clinical laboratories and databases now use:

1. **Pathogenic**: There is strong or very strong evidence that this variant causes disease.
2. **Likely Pathogenic**: There is moderate evidence that this variant causes disease.
3. **Uncertain Significance** (VUS): Evidence is insufficient or conflicting; we don't know yet.
4. **Likely Benign**: There is moderate evidence that this variant does not cause disease.
5. **Benign**: There is strong or very strong evidence that this variant does not cause disease.

These tiers sound simple, but the reasoning behind them is complex. Let's break down how scientists actually build the evidence that puts a variant into one of these categories.

## What Evidence Goes Into Classification?

Classifying a variant isn't a matter of opinion or intuition. Scientists weigh multiple lines of evidence, each of which points toward or away from pathogenicity.

### Population Frequency Data

One of the simplest but most powerful pieces of evidence is how common the variant is in the general population. If a variant is present in 5% of the world's population, it's probably not causing a severe genetic disease—because if it did, we'd see a lot more sick people.

Scientists look at databases like gnomAD (the Genome Aggregation Database), which contains genetic information from over 140,000 people. If a variant is found at high frequencies in gnomAD, especially in people of the same ancestry as the person being tested, that's strong evidence against pathogenicity.

However, this can be tricky. A variant might be rare overall but more common in specific populations. That's important context.

### Functional Studies

What does the variant actually do to the protein? Some variants change a critical amino acid in a protein, potentially breaking its function. Others change a synonymous (quiet) position that doesn't alter the amino acid at all and likely has no effect.

Scientists use computational predictions to estimate whether a change is likely to be damaging. Tools like PolyPhen-2 and SIFT predict, based on how the mutation changes the protein's structure or chemistry, whether it's likely to harm function. These are useful but not perfect—they're educated guesses, not experiments.

Real functional studies—where researchers actually test the variant in a lab—are much stronger evidence. They might put the mutant protein in a cell, measure whether it still works, and see if cells with the variant behave differently. But these studies are expensive and time-consuming, so many variants don't have them.

### Segregation Studies

This comes from family analysis. If a variant "segregates with disease"—meaning affected family members have it and unaffected relatives don't—that's evidence for pathogenicity. But if you see people in your family who carry the variant but are completely healthy, that weakens the case for pathogenicity.

The challenge is that many genetic conditions show incomplete penetrance (more on that in another post), meaning some people with the variant are affected and others aren't. So even good segregation data can be complex to interpret.

### Computational Predictions

Beyond PolyPhen and SIFT, there are dozens of tools that try to predict variant effects: CADD scores, conservation scores, and AI-based predictors. These are useful signals but shouldn't be the only evidence. A variant could score as "probably damaging" computationally but turn out to be benign in real life, and vice versa.

Allelio includes some of these scores in its analysis, but they're meant to be one piece of the puzzle, not a definitive answer.

### Case Reports and Literature

Medical journals contain case reports where clinicians describe patients with a disease caused by a specific variant. Multiple independent case reports, especially if they describe similar clinical presentations, strengthen the evidence that a variant is pathogenic.

But there's a publication bias here: interesting findings get published, and boring findings (variant doesn't cause disease) are less likely to appear in the literature. This can skew the evidence slightly toward pathogenicity.

## How Laboratories Actually Make the Decision

In practice, a clinical genetics laboratory—whether at a hospital, research institution, or genetic testing company—interprets all this evidence together using ACMG guidelines. An expert geneticist or pathologist sits down with the evidence for a particular variant in a particular gene and assigns it to one of the five tiers.

The ACMG has laid out specific "rules" to help standardize this process. For example:

- **Very Strong pathogenicity points** (enough by themselves to call a variant pathogenic): A truncating variant (frameshift, nonsense mutation) in a gene that shows no truncating variants in the healthy population.

- **Strong pathogenicity points**: Multiple lines of evidence (damaging computational prediction + segregation in families + population data all pointing the same way).

- **Benign evidence points**: High frequency in unaffected populations, especially in the same ancestry as the person tested.

This is deliberately systematic, but it still requires human judgment.

## Why Labs Sometimes Disagree

Here's an important reality: **different laboratories sometimes classify the same variant differently.** This isn't because one is right and one is wrong; it's because:

1. **They have different data.** Lab A might have access to segregation data from families; Lab B might not.
2. **They weight the evidence differently.** Expert opinions can legitimately vary on how strong a piece of evidence is.
3. **They update their classifications over time.** As new research emerges, evidence changes.
4. **They focus on different conditions.** A variant might be pathogenic for one disease but benign for another; different labs might emphasize different associations.

This is why ClinVar, the database Allelio uses, shows submissions from multiple labs. You might see that Lab X classifies a variant as "Pathogenic" while Lab Y calls it "Likely Benign." That's not a bug in ClinVar; it's reflecting real disagreement in the field.

## What Review Status and Stars Mean

ClinVar assigns a **review status** to each variant classification, shown as a number of stars:

- **No stars**: Submitted by a single submitter with no independent review.
- **1 star**: Reviewed by criteria provided by a database (like NCBI), but not independently verified.
- **2 stars**: Reviewed by a criteria-based review process AND one expert panel, or multiple submitter assertion categories.
- **3 stars**: Highest confidence—reviewed by an expert panel and meeting the highest standard of evidence.

More stars mean the classification has been more rigorously reviewed. If you see a variant classification with no stars from a single lab, be more cautious about interpreting it than if you see three-star evidence from multiple labs.

Allelio aims to highlight more confident classifications, but it's good to know that lower-confidence classifications might change.

## Classifications Change Over Time

Here's something many people don't realize: classifications can and do change as new evidence emerges.

A variant classified as "Uncertain Significance" five years ago might be reclassified as "Likely Benign" today because researchers found it's more common than previously thought. Or new functional studies might move it toward pathogenic.

This isn't scientists being wishy-washy. It's evidence-based medicine evolving with evidence. If you had genetic testing years ago and got a particular classification, it's worth checking back occasionally to see if the classification has been updated.

## What This Means for Your Allelio Results

When Allelio reports a variant and its clinical significance, you're looking at a carefully considered assessment based on multiple lines of evidence. The classification isn't perfect, but it represents the best current understanding of whether that variant matters for health.

If you see "Pathogenic," that's strong evidence the variant affects disease risk. If you see "Uncertain Significance," that means the scientific evidence isn't yet clear, and that's okay—research is ongoing. The key is reading and interpreting the evidence, not just accepting a label.

---

*Allelio is for educational purposes only and is not a substitute for medical advice. Learn more at [allelio.org].*
