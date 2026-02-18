# What Is a P-Value? Understanding the Statistics Behind Your GWAS Results

When you look at genetic study results in Allelio, you'll encounter something called a p-value. It might look something like this: "p = 0.0000001" or expressed in scientific notation as "p = 1×10⁻⁷". If you're not trained in statistics, p-values can seem like mysterious numbers that gatekeep understanding. But the core concept is actually intuitive. Let's demystify it.

## The Intuitive Explanation: How Surprising Is This?

A p-value answers one specific question: "If there were actually no relationship between this genetic variant and this trait, how surprising would our results be?"

Think of it this way. Imagine you flip a coin 20 times and get 15 heads and 5 tails. That's weird—you'd expect roughly 10 of each. But how weird? It's unusual, but not impossible. A fair coin can occasionally produce unbalanced results just by chance. A p-value quantifies exactly how unlikely your results would be if nothing unusual were going on.

In genetics, researchers conduct huge studies with hundreds of thousands of people. They look at thousands of genetic variants. For each variant, they ask: "Is this variant more common in people with this disease compared to people without?" If a variant is truly unrelated to the disease, the frequency should be roughly the same in both groups. But random variation exists everywhere. Sometimes you'll see differences just by chance.

A p-value measures how unlikely your observed difference would be if the variant truly had no effect. A very small p-value means your results are so extreme that they'd rarely occur by chance alone. A large p-value means your results are the kind of thing you'd commonly see even with a coin flip.

## The Standard Threshold: 5×10⁻⁸

This brings us to one of the strangest conventions in science: the magic number **5×10⁻⁸** (that's 0.00000005).

This threshold emerged because of a correction problem. When researchers do a genome-wide association study (GWAS), they test roughly one million SNPs. If they used a standard p-value threshold of 0.05 for each test, they'd expect about 50,000 false positives (0.05 × 1,000,000) just by random chance. That's unacceptable.

To fix this, statisticians applied a correction called the Bonferroni correction: divide your p-value threshold by the number of tests. So 0.05 divided by 1,000,000 = 5×10⁻⁸. A SNP must reach this threshold to be considered "genome-wide significant."

What does this mean in plain English? A p-value of 5×10⁻⁸ means: "If this variant truly had no effect, we'd see results this extreme less than once in every 20 million similar studies." That's a pretty safe bet.

## What "Genome-Wide Significance" Really Means

When you see a SNP marked as "genome-wide significant" in Allelio, it means the association is strong enough that it's unlikely to be a false positive from random testing variation across the entire genome.

But here's what it *doesn't* mean:
- It doesn't mean the variant definitely causes the trait
- It doesn't mean the effect is large
- It doesn't mean you'll definitely experience the outcome
- It doesn't mean the result will replicate in other populations
- It doesn't mean the finding is clinically important

Genome-wide significance is a statistical criterion. It's saying "this finding is unlikely to be noise." That's all. It's a necessary condition for trusting a finding, but not sufficient on its own.

## What P-Values Do NOT Tell You

This is absolutely critical, and it's where many people misunderstand statistics.

**A small p-value does not indicate effect size.** You can have a p-value of 10⁻¹⁵ (extraordinarily small) and still have an effect that's biologically irrelevant. This happens when you have a huge sample size. With enough people, you can detect that a variant increases risk by 1%—technically real, statistically certain, but practically meaningless.

**A small p-value does not indicate clinical importance.** Imagine a study of one million people showing that a variant increases your heart disease risk from 5% to 5.2%. The p-value might be tiny. But the absolute increase in risk is only 0.2 percentage points. That's statistically significant but practically modest.

**A small p-value does not indicate that something is probable.** This is subtle but crucial. A p-value of 0.001 doesn't mean "there's a 99.9% chance this effect is real." It means "if there were no effect, we'd see data this extreme 0.1% of the time." These sound similar but are mathematically different. With enough samples, you can get a tiny p-value for a real but trivial effect.

## Why Do Some Findings Have Tiny P-Values and Tiny Effects?

This seems paradoxical, but it's actually expected.

Large studies are powerful. They can detect small effects with high confidence. If you study 500,000 people instead of 5,000, you have 100 times more statistical power. You can detect effects 10 times smaller.

So in modern GWAS studies involving hundreds of thousands of people, most genome-wide significant findings have very small effects. A variant might increase disease risk from 50% to 50.5%. The p-value is astronomical. But the effect size—the magnitude of the association—is tiny.

This is one reason we need other tools beyond p-values. Effect size matters. So does biological plausibility. So does replication in independent studies.

## How to Read P-Values in Allelio Results

When you use Allelio to analyze GWAS findings, here's what to look for:

**P-value under 5×10⁻⁸?** The finding passes the genome-wide significance threshold. It's statistically robust.

**But check the effect size too.** Allelio should show you the odds ratio or beta coefficient. A genome-wide significant finding with an odds ratio of 1.01 (1% increased risk) is less impressive than one with an odds ratio of 1.5 (50% increased risk), even though the p-value might be smaller in the former case.

**Check the sample size.** Huge studies with huge p-values are standard now. A p-value of 10⁻¹⁰⁰ just means the researchers studied millions of people.

**Look at replication.** Has this finding been replicated in independent studies? Multiple papers reporting the same association is more convincing than a single study, regardless of the p-value.

**Consider ancestry.** Was the study conducted in a population similar to yours? A strongly significant finding from a European-only study may not apply equally to other populations.

## The Bottom Line

P-values are tools for filtering noise. A very small p-value suggests a finding is unlikely to be random. But "unlikely to be random" is a low bar. The real questions—whether an effect is large, whether it's important, whether it applies to you—require looking beyond the p-value.

Allelio makes this easier by showing p-values alongside other context: effect sizes, study populations, biological plausibility. Use the p-value as a starting point, but don't let it be the endpoint of your interpretation. Statistical significance and practical significance are not the same thing.

---

*Allelio is for educational purposes only and is not a substitute for medical advice. Learn more at [allelio.org].*
