# Pathogenic vs. Benign: What ClinVar Classifications Actually Mean for Your DNA Results

When you look at your Allelio results, you'll see words like "pathogenic," "likely benign," and "uncertain significance" next to your variants. These aren't casual labels — they're standardized clinical classifications that carry specific meanings. Understanding them is essential to making sense of your results without overreacting or dismissing something important.

## The Five-Tier System

The classification system used in ClinVar was established by the American College of Medical Genetics and Genomics (ACMG) and the Association for Molecular Pathology (AMP) in a landmark 2015 guideline. It defines five categories for classifying genetic variants based on their relationship to disease.

**Pathogenic** is the strongest classification. It means there is sufficient evidence — from multiple lines of research including functional studies, family segregation data, population data, and computational predictions — that this variant causes or significantly contributes to disease. When a laboratory classifies a variant as pathogenic, they're saying the evidence meets a high bar.

**Likely pathogenic** means the evidence is strong but falls just short of the threshold for a definitive "pathogenic" call. The ACMG guidelines specify that "likely pathogenic" corresponds to a greater than 90% certainty that the variant is disease-causing. In clinical practice, "likely pathogenic" variants are generally treated with the same seriousness as "pathogenic" ones.

**Uncertain significance (VUS)** is the classification that causes the most confusion and anxiety. It means there isn't enough evidence to classify the variant as either harmful or harmless. This is extremely common — many variants simply haven't been studied enough, or the existing evidence is contradictory. A VUS is not a reason to panic. It's a reflection of the current limits of scientific knowledge.

**Likely benign** means the evidence suggests the variant is not disease-causing, with greater than 90% certainty. These variants are generally considered clinically unactionable.

**Benign** means there is strong evidence that the variant does not cause disease. Common variants present in large portions of the population are often classified as benign.

## What "Pathogenic" Does and Doesn't Mean

This is where misunderstanding is most common, and most dangerous.

A "pathogenic" classification means the variant has been evaluated and found to have sufficient evidence linking it to disease. It does not mean you have that disease. It does not mean you will develop that disease. It does not mean you need to do anything specific right now.

There are several reasons for this distinction.

**Penetrance varies.** Penetrance is the probability that a person carrying a pathogenic variant will actually develop the associated condition. Some pathogenic variants have high penetrance (most carriers develop the condition), but many have reduced or incomplete penetrance (only a fraction of carriers are affected). The penetrance of a variant can also differ by age, sex, environment, and genetic background.

**Zygosity matters.** Many conditions are recessive, meaning you need pathogenic variants on both copies of the gene (one from each parent) to be affected. If you carry only one pathogenic copy and one normal copy, you're a carrier — you can pass the variant to your children, but you typically don't have the condition yourself.

**Context is everything.** A pathogenic variant in BRCA1 has very different implications from a pathogenic variant in a gene associated with earwax type. The gene, the condition, the inheritance pattern, your family history, and dozens of other factors all matter.

## The Uncertain Significance Problem

VUS classifications are by far the most common result in clinical genetics, and they're a source of enormous frustration for patients and clinicians alike.

When you see a VUS in your Allelio results, the most accurate interpretation is: "Science doesn't know yet." The variant hasn't been seen enough times in enough contexts to draw a conclusion. Maybe future research will reclassify it as benign. Maybe as pathogenic. For now, it sits in limbo.

The clinical guidance for VUS variants is generally to not act on them — don't change your medical care based on a VUS. But that doesn't mean they should be ignored entirely. Some clinicians recommend periodic check-ins as databases are updated, because VUS variants are frequently reclassified as new evidence emerges.

In ClinVar specifically, VUS classifications are common partly because of how submissions work. Different laboratories may classify the same variant differently, and a variant might be VUS from one submitter while another has more data. The review status in ClinVar (one star, two stars, expert panel, etc.) helps indicate how much consensus exists.

## Beyond the Five Tiers

ClinVar also contains variants with other classification terms you might encounter in Allelio.

**Risk factor** means the variant is associated with increased susceptibility to a condition but is not by itself sufficient to cause disease. Many APOE4 variants fall into this category — carrying them increases your statistical risk for Alzheimer's disease, but the majority of carriers never develop it.

**Protective** means the variant is associated with reduced risk for a condition. These are the "good news" variants — for example, certain variants that appear to reduce the risk of malaria, Type 2 diabetes, or coronary artery disease.

**Drug response** means the variant affects how you respond to a specific medication. These pharmacogenomic variants can be among the most actionable findings, because they can directly inform prescription choices — but only when interpreted by a healthcare provider.

**Association** means a statistical link has been found between the variant and a trait or condition, but the evidence hasn't been fully evaluated for clinical significance. Many GWAS findings fall into this category.

## How Allelio Presents Classifications

Allelio organizes your results by clinical significance, showing the most potentially important variants first. Pathogenic and likely pathogenic variants appear at the top, color-coded in red. Risk factors appear in orange. Traits and associations in blue. Benign and protective variants in green.

This ranking helps you focus your attention, but it's important not to stop at the color. For every variant, look at the gene, the associated condition, the review status, and (if available) the AI explanation. A "pathogenic" variant in a gene associated with a mild, manageable condition is very different from a "pathogenic" variant in BRCA1 or TP53.

And remember: if anything in your results concerns you, the right next step is a conversation with a genetic counselor — not a late-night spiral through Google search results. Genetic counselors are specifically trained to interpret these classifications in the context of your personal and family medical history.

## Classifications Change Over Time

One final point worth emphasizing: ClinVar classifications are not permanent. As new research is published, as more patients are tested, and as functional studies are completed, variants get reclassified. A variant that was VUS five years ago might now be classified as benign or pathogenic.

This is why Allelio includes a database update command. Running `allelio update` downloads the latest versions of ClinVar and the GWAS Catalog, ensuring your analysis reflects the most current scientific understanding. We recommend updating before each new analysis.

---

*Allelio is for educational purposes only and is not a substitute for medical advice. Learn more at [allelio.org].*
