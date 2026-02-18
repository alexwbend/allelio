# Polygenic Risk Scores Explained: How Scientists Combine Thousands of Tiny Genetic Effects

You've heard about "genetic risk" for disease, but traditional genetics talks about single genes with large effects—BRCA1 for breast cancer, or huntingtin for Huntington's disease. Those are the exceptions. Most complex diseases like heart disease, diabetes, and Alzheimer's involve thousands of genetic variants, each with tiny individual effects. Putting these together creates a polygenic risk score, or PRS. It's a powerful tool, but also a frequently misunderstood one.

## What Is a Polygenic Risk Score?

A polygenic risk score aggregates the effects of many genetic variants into a single number representing overall genetic risk. Instead of looking at one gene, you're looking at thousands—or even millions—of variants simultaneously.

Here's how it works in principle:

1. A large genetic study identifies variants associated with a trait (say, heart disease)
2. Each variant gets a weight based on its effect size (bigger effects = bigger weights)
3. For each person, you count how many risk alleles they carry at each position
4. You multiply each count by the variant's weight and sum them up
5. The result is a score reflecting overall genetic predisposition

A person with many risk alleles across many variants gets a high score. A person with few risk alleles gets a low score. The score doesn't predict whether you'll get the disease, but it indicates whether your genetic background puts you at higher or lower risk compared to the population average.

## How PRS Is Currently Used

Polygenic risk scores have moved from pure research into limited clinical applications. Here's where they're actually being used:

**In research.** PRS helps scientists understand the genetic architecture of diseases. It identifies people at high genetic risk for study enrollment. It estimates how much of disease variation is explained by common genetic variants.

**In early clinical trials.** Some medical centers use PRS to stratify participants—identifying people at high genetic risk who might benefit from preventive screening or interventions.

**In direct-to-consumer testing.** A few companies now offer PRS calculations for traits like heart disease risk, though clinical utility is still being evaluated.

**In future clinical medicine.** As evidence accumulates, PRS may become more integrated into risk assessment for common diseases, potentially alongside traditional risk factors like blood pressure and cholesterol.

But here's the honest truth: for most conditions, polygenic risk scores are not yet clinically standard. They're not replacing traditional risk assessment. They're a promising tool under development.

## What PRS Can and Cannot Do

Understanding the limitations is just as important as understanding the potential.

**What PRS can do:**
- Rank people by genetic predisposition relative to each other
- Identify people in the top 5-10% of genetic risk for further evaluation
- Provide one data point in a comprehensive risk assessment
- Help researchers understand genetic contributions to disease
- Potentially guide prevention strategies (though evidence is still accumulating)

**What PRS cannot do:**
- Predict whether you will develop a disease (individuals are too variable)
- Replace traditional clinical risk factors like blood pressure, cholesterol, smoking status
- Account for epigenetics, which we discussed in our last post
- Account for gene-environment interactions (your genes and lifestyle together)
- Tell you about rare variants with large effects
- Work equally well across all ancestries

That last point is critical and deserves emphasis.

## The Ancestry Problem: Why PRS Is Biased

Most GWAS studies, and therefore most PRS models, were developed in people of European ancestry. This creates a serious problem: polygenic risk scores work better in the ancestry group they were trained on and worse in other groups.

Here's why. Remember from our earlier post that variant frequencies vary between populations. A variant might be common in Europeans but rare in Africans or East Asians. If a PRS model was trained in Europeans and then applied to someone with African ancestry, the variant frequencies don't match. The model's weights—calibrated on European data—may not apply.

Studies have shown that PRS predicts risk more accurately in European ancestry individuals than in African ancestry individuals, even for the same disease. This means that if you have non-European ancestry and you see a PRS calculated from a European-trained model, you should be skeptical about its applicability.

Population-specific PRS models exist but are less common because they require huge studies in each ancestry group. This is a major ongoing limitation in the field.

## Why Most GWAS Effect Sizes Are Tiny

If you've been reading Allelio results, you've noticed that most individual genetic variants have odds ratios between 1.0 and 1.5. These are small effects. A single variant might increase disease risk by 10-20%. So how do thousands of these combine into meaningful predictive information?

The math of aggregation. If you have 1,000 variants each increasing risk by 1%, the combined effect becomes substantial. The individual droplets add up to a bucket. With 10,000 variants (which is typical for modern PRS), you can aggregate enough effect to meaningfully distinguish high-risk from low-risk individuals, even though individual variants are small.

But here's the catch: this only works if you actually have genotype data for all those variants. Allelio analyzes your raw DNA file, which typically includes hundreds of thousands to a million SNPs—plenty for PRS calculation in principle. But not all PRS models use the exact same variants, and some variants may not be well-represented in consumer chips.

## Why Allelio Doesn't Calculate PRS (Yet)

Allelio is currently designed for analyzing individual genetic findings and learning about GWAS results. Calculating a full polygenic risk score for complex diseases isn't something Allelio does by default, and here's why:

1. **No single consensus PRS.** Different researchers use different variants, different weights, different ancestries. Which one do you calculate?

2. **Ancestry matching is critical.** To be clinically meaningful, a PRS should match your ancestry. A European-trained PRS applied to someone with Asian ancestry could be misleading.

3. **Clinical utility not yet proven.** For most conditions, PRS doesn't yet improve risk prediction beyond traditional clinical factors. Adding it to Allelio would suggest clinical utility that doesn't yet exist.

4. **Ethical questions.** Should consumer tools provide PRS? What's the risk of misinterpretation? What's the benefit?

That said, Allelio's architecture could accommodate PRS in the future—perhaps allowing users to calculate ancestry-matched scores from published models, with appropriate caveats about interpretation.

## What Would Be Needed for Allelio to Calculate PRS

If Allelio were to add PRS functionality, several things would be necessary:

- **Multiple published PRS models** for different conditions, with transparency about which variants are included and which ancestry the model was trained on
- **Ancestry inference** to ensure the selected PRS matches your background
- **Clear interpretation guidance** emphasizing that a high PRS score doesn't mean you will develop the disease—only that your genetic background places you at higher relative risk
- **Comparison to clinical risk factors** showing how genetic risk stacks up against age, blood pressure, cholesterol, smoking status, etc.
- **Caveats about generalization** especially if the user's ancestry differs from the study population

This is non-trivial software and communication work. It would be valuable, but it requires doing it right.

## The Future of PRS in Medicine

Polygenic risk scores are advancing rapidly. As more massive studies are conducted, as models are developed for diverse ancestries, and as clinical evidence accumulates, PRS will likely become more integrated into medical practice.

But the maturation of this field will likely follow this timeline:

- **Near term (1-2 years):** More ancestry-specific PRS models. Better integration into clinical research. Consumer tools offering calculated scores with appropriate disclaimers.
- **Medium term (3-5 years):** PRS integrated into routine cardiovascular risk assessment. Potential use for cancer risk stratification.
- **Longer term (5+ years):** PRS combined with epigenetics, environment, and lifestyle data for truly personalized risk prediction. Clinical guidelines incorporating PRS for selected conditions.

But even then, PRS will be a tool among many, not a replacement for comprehensive health assessment.

## The Bottom Line

Polygenic risk scores are conceptually simple: aggregate many small genetic effects into one number. But their real-world utility is more nuanced. They show promise for research and potentially for clinical risk stratification, but they're not yet ready for routine clinical use in most conditions. They work better in some ancestries than others. And they can't tell you whether you'll develop a disease—only where you fall on the population distribution.

If you use Allelio to explore your genetics, think of it as learning about individual variants and the GWAS studies that discovered them. If you ever encounter a polygenic risk score, treat it as one piece of information in a larger picture that includes your personal and family history, clinical risk factors, and lifestyle.

Your genes matter, but they're just one thread in the tapestry of your health.

---

*Allelio is for educational purposes only and is not a substitute for medical advice. Learn more at [allelio.org].*
