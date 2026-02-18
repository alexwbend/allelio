# What Is Linkage Disequilibrium? Why Nearby Genes Are Often Inherited Together

When you look at your Allelio results, you might see something unexpected: you have a variant associated with a certain condition, but when you dig deeper, that variant might not actually be the causal variant—the one directly causing the problem. Instead, you might be seeing a variant that's near the real culprit. Understanding **linkage disequilibrium** explains why this happens and why it's actually important for genomic science.

Linkage disequilibrium (LD) is a concept that seems abstract at first, but it's fundamental to how genome-wide association studies (GWAS) work, and it matters for interpreting genetic results correctly.

## What Linkage Disequilibrium Actually Is

Let's break the term down:

- **Linkage**: In genetics, this refers to variants being physically close together on a chromosome. Variants that are close to each other are "linked."
- **Disequilibrium**: This means things are not in random association.

**Linkage disequilibrium** is the tendency for variants that are located near each other on a chromosome to be inherited together more often than would happen by random chance.

Here's a simple example: Imagine two nearby variants on a chromosome, Variant A and Variant B. If they were inherited completely randomly and independently, you'd expect to see them together in certain proportions based on their individual frequencies. But in reality, if you inherited Variant A from your mother, you're more likely to also inherit Variant B from that same mother—because they're located close together on the same physical chromosome, and chromosomes tend to be inherited as units.

## Why Variants Travel Together: The Chromosome as a Package

The reason for linkage disequilibrium comes down to how chromosomes are inherited.

When your parent passes a chromosome to you, they don't shuffle all 3 billion letters and pick random ones. They pass along a stretch of the chromosome mostly intact. Over time—across many generations—chromosomes do get shuffled through a process called recombination (where two chromosomes exchange pieces during the formation of sperm and egg cells). But this shuffling is random, and nearby variants don't get separated as easily as distant ones.

Think of a chromosome like a bead necklace. If two beads are next to each other, they're almost always passed down together. Beads that are far apart might get separated by cutting and rearranging the necklace, but next-door neighbors stay together.

This is why variants that are close together show LD—they travel together through generations and through populations. Variants that are far apart have had more time and opportunity to get separated, so they show less LD.

## Tag SNPs and GWAS: Why LD Matters in Practice

Here's where LD becomes practically important: **genome-wide association studies** (GWAS) don't actually genotype every variant in the human genome. That would be prohibitively expensive and unnecessary.

Instead, GWAS uses a clever strategy: they genotype a subset of variants called **tag SNPs**. These are variants that, due to linkage disequilibrium, are good proxies for many other nearby variants.

Here's the logic: if Variant A and Variant B are in strong LD (meaning they're almost always inherited together), then genotyping just Variant A tells you a lot about whether people have Variant B. You get information about both variants by testing just one.

This is why GWAS results often point to a genomic region rather than a single variant. When a GWAS identifies a "hit"—an association between a variant and a disease—that variant might be the causal variant, or it might be a tag SNP that's in LD with the true causal variant. You don't know without further investigation.

## The Tag SNP Isn't Always the Culprit

This is an important point for interpreting results: just because a GWAS identified a variant doesn't mean that variant directly causes the association.

Imagine a GWAS finds that Variant X is associated with heart disease. Researchers might initially think Variant X affects heart disease risk. But follow-up studies might reveal that Variant X isn't actually doing anything—it's just in LD with Variant Y, a few hundred base pairs away, which is the real culprit.

This is why GWAS results are a starting point, not an answer. They identify genomic regions of interest. Then researchers do fine mapping—trying to figure out which variant in the region is actually causal.

## LD Varies Across the Genome and Across Populations

The strength of LD isn't uniform everywhere. Several factors affect it:

### Physical Distance
Generally, variants that are very close together (within a few thousand base pairs) are in strong LD. Variants that are millions of base pairs apart might show little LD at all. But the exact distance where LD becomes weak varies across the genome.

### Recombination Hotspots
Some regions of the genome are recombination hotspots—places where chromosomes are more likely to get shuffled. Variants on opposite sides of a hotspot show less LD even if they're not very far apart. Other regions are recombination deserts where variants remain linked even if they're somewhat distant.

### Population History and Size
Different populations have different LD patterns. European populations that went through bottlenecks (where the population size dramatically shrank) often have longer stretches of LD because there's been less recombination and shuffling.

African populations, which didn't go through as many bottlenecks, often show shorter LD blocks.

This has an important implication: a variant that's a good tag SNP in Europeans might not be a good tag SNP in Africans or East Asians. This is one reason why GWAS results developed in European populations don't always translate well to other populations.

## Recombination: How LD Breaks Down Over Generations

Linkage disequilibrium gradually breaks down over generations through recombination. Each generation, some chromosomes shuffle. Over many generations, even variants that started out tightly linked get separated.

This is why you can look at very ancient DNA—from people who lived thousands of years ago—and see that variants are in LD in patterns different from modern humans. The LD patterns literally tell us about population history.

It also explains why you might inherit a specific haplotype (a block of variants in LD) from your parent, but your parent inherited a different haplotype—recombination shuffled things in the generation before.

## What This Means for Interpreting Allelio Results

When Allelio finds a GWAS association at a particular variant, remember:

- That variant might be the causal variant directly affecting your health.
- Or it might be a tag SNP in LD with the true causal variant.
- Allelio will note this where possible, but you should be aware that GWAS hits point to regions, not definitively to individual variants.

Also remember:
- The association found in GWAS might be stronger or weaker in your specific population.
- Your other genetics, your environment, and your specific variants might mean the association in the GWAS doesn't apply exactly to you.

## Why LD Matters for Your DNA Health Journey

Understanding linkage disequilibrium helps you appreciate a reality of genomic science: we often don't know exactly which variant causes a disease association. We know variants in a region are associated, but identifying the causal variant is harder than it seems.

This is why genetic research is ongoing. LD helps explain why finding a variant in your genome doesn't immediately explain whether and how it affects your health. The variant might be a hint, a pointer to a region of interest, not a direct cause.

For Allelio specifically, understanding LD helps you interpret GWAS results appropriately. When you see a GWAS variant flagged, you're seeing a signal from a region—valuable information, but not a complete answer.

The good news is that scientists are increasingly doing fine-mapping studies to identify causal variants. Over time, we'll move from "this region is associated with disease" to "this specific variant causes disease."

In the meantime, understanding linkage disequilibrium helps you think clearly about what genetic data really tells us—and what it doesn't.

---

*Allelio is for educational purposes only and is not a substitute for medical advice. Learn more at [allelio.org].*
