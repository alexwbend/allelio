# Consumer DNA Chips vs. Clinical Genetic Testing: What's the Difference and Why It Matters

Allelio works with raw DNA data from consumer companies like 23andMe and AncestryDNA. These use a technology called microarray genotyping. If you've ever been concerned about a genetic condition and your doctor ordered "genetic testing," that was likely something different: clinical sequencing. The technologies measure different things, have different error rates, and different clinical implications. Understanding these differences helps you know when consumer data is informative and when you need clinical-grade testing.

## How Consumer Microarray Genotyping Works

Consumer DNA tests use microarray chips, also called SNP chips. Here's the process in plain English:

1. **DNA extraction.** A saliva sample is processed to extract DNA.

2. **DNA fragmentation and amplification.** The DNA is cut into pieces and copied millions of times using PCR (polymerase chain reaction).

3. **Chip hybridization.** The amplified DNA is applied to a microarray chip—a small glass or silicon slide with hundreds of thousands to millions of tiny spots. Each spot contains a probe: a short piece of DNA designed to match a specific location in the human genome.

4. **Binding.** Where your DNA matches a probe, it binds. Unmatched DNA washes away.

5. **Fluorescence detection.** The bound DNA is marked with fluorescent dyes. A scanner reads which spots have fluorescence, identifying which genetic variants you carry.

6. **Genotype calling.** Software analyzes the fluorescence intensity to determine whether you're homozygous for the reference allele, heterozygous, or homozygous for the alternate allele.

This process is elegant and scalable. A single chip can measure a million variant positions quickly and affordably. This is why companies can offer genetic testing for $100-200.

## How Clinical Genetic Sequencing Works

Clinical genetic testing typically uses DNA sequencing, which works by a different principle:

1. **DNA fragmentation.** Genomic DNA is cut into small pieces.

2. **Library preparation.** The fragments are prepared for sequencing—adapters are added, primers are attached.

3. **Sequencing.** Using one of several sequencing technologies (Illumina is most common), the DNA fragments are read base-by-base. Instead of testing pre-determined positions like a microarray, sequencing reads essentially the entire DNA sequence.

4. **Alignment.** The millions of short reads are computationally assembled and aligned to a reference genome.

5. **Variant calling.** The software identifies where your sequence differs from the reference genome—insertions, deletions, substitutions, anything.

6. **Interpretation.** For clinical testing, each identified variant is assessed: Is it known? Is it pathogenic? Is it in a gene relevant to the clinical question? Is it confirmed in a validated database?

Sequencing is more comprehensive and more expensive ($1,000-5,000+ for clinical whole genome sequencing).

## What Each Technology Can and Cannot Detect

This is where the practical differences become critical.

**Microarray can detect:**
- Variants at the specific positions on the chip (typically common variants with frequency >1%)
- Single nucleotide substitutions at interrogated sites
- Some larger variations if they're represented on the chip
- Copy number variations (sometimes, depending on chip design)

**Microarray cannot detect:**
- Variants at positions not on the chip (most rare variants)
- Novel variants (new mutations not previously identified)
- Small insertions or deletions at unmeasured positions
- Structural variations not represented on the chip
- Changes in repetitive DNA regions

**Sequencing can detect:**
- All substitutions (assuming adequate coverage)
- Insertions and deletions of any size
- Structural variations (large rearrangements)
- Novel variants (anything different from reference, even if never seen before)
- Changes in repetitive and hard-to-sequence regions (though less reliably)

**Sequencing cannot detect (easily):**
- Copy number variations (needs special analysis)
- Epigenetic modifications (sequencing reads DNA, not methylation)
- Phase information (which alleles are inherited together on the same chromosome)

## Error Rates: When Tests Disagree

Microarray genotyping error rates are typically 1 in 10,000 bases or lower. This is actually quite good. However, the error rate varies by variant. Common variants are called very accurately; rare variants on the chip are called less accurately (paradoxically, because they're rare in the reference population used to calibrate the chip).

Clinical sequencing error rates depend on coverage depth (how many times each position is read) and the sequencing technology. Modern clinical whole genome sequencing typically achieves error rates of 1 in 10,000 to 1 in 100,000 bases, but this varies by position and variant type.

In practice, what matters is: **which variants matter clinically?** A false positive call on a population-frequency variant in Allelio might be interesting but not actionable. A false positive or false negative call on a pathogenic variant in a clinical setting could have serious consequences.

This is why clinical testing requires:
- Validation in a certified lab
- Confirmation of clinically significant variants
- Professional interpretation

## Why Consumer Results Should Be Confirmed Clinically

If Allelio identifies a finding that concerns you—say, a variant associated with increased breast cancer risk—what should you do?

The short answer: get professional genetic counseling and potentially clinical confirmation testing.

Here's why:

1. **Allelio analyzes research data.** The GWAS studies it draws from may not apply to your situation. The variants may be associated with risk but not deterministic. The research might be population-specific.

2. **Clinical assessment considers many factors.** Your doctor or genetic counselor looks at your personal history, family history, age, environmental exposures, and other medical information. A variant in isolation doesn't tell this story.

3. **Clinical testing is definitive.** If you carry a BRCA1 mutation (associated with breast and ovarian cancer), that's important information that should be confirmed using clinical sequencing with proper documentation and interpretation.

4. **Rare or novel variants need assessment.** If Allelio flags something unusual, clinical sequencing might be needed to definitively characterize it.

5. **Medically-actionable findings deserve professional guidance.** Genetic counselors can explain what a variant means, what screening or prevention is recommended, and how it affects your family.

## CLIA and CAP Accreditation: What It Means

You may hear that clinical labs are "CLIA-certified" or "CAP-accredited." What does this mean?

**CLIA (Clinical Laboratory Improvement Amendments)** is a U.S. federal regulatory requirement for labs performing clinical testing on human samples. CLIA certification ensures:
- Proper quality control procedures
- Proficiency testing (labs are regularly tested with known samples)
- Staff qualifications
- Proper result reporting and documentation

**CAP (College of American Pathologists)** is an additional accreditation that's more rigorous than CLIA. CAP-accredited labs undergo intensive external audits and hold themselves to higher standards.

Consumer genetic companies typically don't pursue CLIA/CAP accreditation for all their tests. Some offer CLIA-certified ancestry or carrier screening, but not all services are clinically validated.

This doesn't mean consumer results are wrong—just that they haven't been subjected to the same regulatory oversight as clinical lab results.

## When to Upgrade from Consumer to Clinical Testing

When should you move beyond Allelio and consumer data?

**Definitely get clinical testing if:**
- You have a strong family history of cancer, heart disease, or other genetic conditions
- You carry a variant associated with a condition you want to screen for
- You're planning medical treatment decisions (like preventive surgery)
- You're pregnant and want to assess risk to your baby
- You have symptoms of a genetic condition

**Consider clinical testing if:**
- Allelio identifies something that worries you
- You want definitive answers about a medically-actionable variant
- Your ancestry differs from the study populations in Allelio's databases

**Consumer testing alone may be sufficient for:**
- Ancestry exploration (no clinical implications)
- General health curiosity
- Research participation
- Understanding your genetic background

## The Role of Allelio in This Landscape

Allelio fits into this ecosystem as an educational tool. It helps you understand what your consumer genetic data means using the latest research. It's not a replacement for clinical testing when medically-relevant questions arise.

Think of Allelio as a bridge: it helps you interpret what consumer genetics can tell you and—importantly—recognize when you should seek professional evaluation.

## The Bottom Line

Consumer microarray chips and clinical sequencing are complementary technologies. Microarrays are affordable, fast, and work well for known variants in well-studied populations. Sequencing is comprehensive and can detect anything, but costs more and requires expert interpretation.

If you're using Allelio to explore your consumer genetic data, you're using a legitimate research tool on legitimately-generated data. But if any findings concern you or might affect medical decisions, the next step is professional consultation and potential clinical confirmation.

Your consumer DNA file is a starting point, not an ending point. Use Allelio to learn from it, but don't let it replace conversations with health professionals when findings matter clinically.

---

*Allelio is for educational purposes only and is not a substitute for medical advice. Learn more at [allelio.org].*
