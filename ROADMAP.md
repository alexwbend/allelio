# Allelio Improvement Roadmap

## v0.2 — Accuracy & Clinical Depth

These improvements focus on making Allelio's variant interpretation closer to what a genetics professional would provide.

### 1. ClinVar Review Status Weighting

Currently Allelio treats all ClinVar entries equally. A variant with a single 1-star submitter gets the same weight as one reviewed by an expert panel with 4 stars. Add review star ratings (0-4) to the database schema, parse the `ReviewStatus` column from ClinVar, and use it to weight significance scores. Expert-panel variants should rank higher than single-submitter ones.

### 2. gnomAD Population Frequency Integration

Add allele frequency data from gnomAD (Genome Aggregation Database). This lets Allelio distinguish between a rare pathogenic variant (seen in 0.001% of people) and a common one (seen in 30%). A variant flagged "pathogenic" that 40% of the population carries is far less alarming than one carried by 0.01%. Download the gnomAD sites VCF or use their API, store frequencies per rsID, and factor frequency into the significance score.

### 3. Gene-Level Grouping & Summaries

Right now results are a flat list of individual variants. Group variants by gene so the user sees "you have 3 variants in BRCA2" rather than three separate entries. Add a gene summary section to the HTML report that explains what each gene does and what it means to have multiple variants in the same gene.

### 4. Improved AI Prompts with Clinical Context

The current AI prompts send minimal context to Ollama. Improve them by including: the variant's ClinVar review status, its population frequency, the gene's known function, whether other variants in the same gene were found, and the specific genotype (homozygous vs heterozygous). This produces much more informative and accurate explanations.

### 5. Zygosity-Aware Interpretation

Allelio currently reports genotype but doesn't factor it into risk. For autosomal recessive conditions, being heterozygous (carrier) is very different from being homozygous (affected). Parse the genotype properly, determine zygosity, cross-reference with ClinVar's inheritance mode data, and adjust the significance score and explanation accordingly.

## v0.3 — Breadth & Advanced Features

These improvements expand Allelio's capabilities beyond basic ClinVar/GWAS lookup.

### 6. PharmGKB Pharmacogenomics Database

Add the PharmGKB database to provide drug-gene interaction data. This tells users things like "your CYP2D6 variant means you may metabolize codeine poorly" or "your VKORC1 genotype suggests sensitivity to warfarin." Download PharmGKB's clinical annotations TSV (free for non-commercial use), add a `pharmgkb` table to the database, and create a "Pharmacogenomics" section in the report.

### 7. Polygenic Risk Score (PRS) Estimates

For common conditions like type 2 diabetes, heart disease, and high cholesterol, no single variant tells the whole story. Implement basic polygenic risk scores by summing the weighted effects of multiple GWAS variants. Use published PRS weights from the PGS Catalog (pgscatalog.org). Add a "Polygenic Risk" section to the report showing estimated relative risk for 5-10 common conditions.

### 8. Ancestry-Aware Filtering

Many variants have different frequencies and clinical significance across populations. Add ancestry context by letting users optionally specify their background (or infer it from their variant profile using principal component analysis against reference populations). Use this to filter out variants that are common/benign in the user's population but flagged because the reference data was primarily European.

### 9. ClinGen Gene-Disease Validity Data

ClinGen (clinicalgenome.org) curates which gene-disease relationships are actually well-established vs. disputed or limited. Integrate ClinGen's gene validity classifications to add confidence indicators. A variant in a gene with "Definitive" ClinGen evidence for a disease is more meaningful than one in a gene with only "Limited" evidence.

### 10. CADD / Computational Pathogenicity Scores

For variants not in ClinVar (novel or rare variants), add computational pathogenicity prediction using CADD scores (Combined Annotation Dependent Depletion). CADD scores predict how damaging a variant is based on conservation, protein impact, regulatory context, etc. A CADD score above 20 means the variant is in the top 1% most deleterious possible substitutions. Download pre-computed CADD scores for known SNPs and use them as a fallback when ClinVar has no entry.

---

## Implementation Notes

- Each improvement should include new tests
- The HTML report template needs updating for each new data section
- Database migrations: adding new tables should not break existing databases — check if table exists before creating
- All new data sources must respect licensing (gnomAD: ODbL, PharmGKB: CC BY-SA for non-commercial, PGS Catalog: open, ClinGen: open, CADD: free for non-commercial)
- The `allelio setup` command should handle new databases as optional downloads that don't block setup if they fail
