# Allelio JOSS Paper — Outline & Draft Template

> **How to use this file:** This is both an outline and a near-ready template for your JOSS
> submission. Sections marked with `[WRITE]` need your input. Sections marked with `[DRAFT]`
> contain suggested prose you can edit. The final `paper.md` you submit will be a trimmed
> version of this — aim for 250–1,000 words total (excluding YAML frontmatter and references).

---

## 1. YAML Frontmatter

```yaml
---
title: "Allelio: Privacy-First Local Genomics Analysis with AI-Powered Interpretation"
tags:
  - Python
  - genomics
  - bioinformatics
  - privacy
  - consumer genetics
  - large language models
  - ClinVar
  - GWAS
authors:
  - name: Alex Kendrick            # [WRITE] Use your full legal name
    orcid: 0000-0000-0000-0000     # [WRITE] Get one free at https://orcid.org/register
    affiliation: 1
affiliations:
  - name: Independent Researcher   # This is standard and accepted by JOSS
    index: 1
date: DD Month 2026                # [WRITE] Submission date, e.g. "15 March 2026"
bibliography: paper.bib
---
```

### Notes on frontmatter
- **ORCID:** Free, takes 2 minutes to register. Strongly recommended by JOSS.
- **Affiliation:** "Independent Researcher" is the standard convention for non-affiliated
  authors. Fully accepted. You can optionally add a city/country, e.g.
  "Independent Researcher, City, Country."
- **Co-authors:** If you bring on a collaborator (e.g., a genetic counselor who reviews
  the safety guardrails, or a bioinformatician who validates the pipeline), add them here.

---

## 2. Summary (~100–150 words)

> *JOSS requirement: "A summary describing the high-level functionality and purpose of the
> software for a diverse, non-specialist audience."*

### Key points to cover

- What Allelio is (one sentence): an open-source Python tool that analyzes consumer
  genotype data entirely on the user's own computer.
- What it does: parses raw data from 23andMe, AncestryDNA, and VCF files; cross-references
  variants against ClinVar (clinical significance) and the GWAS Catalog (trait associations);
  generates plain-English explanations using a local large language model via Ollama.
- What makes it different (the hook): all processing — parsing, database lookup, and AI
  inference — happens locally. No genomic data is ever transmitted over a network.
- Who it's for: researchers, citizen scientists, genetic counseling students, and
  privacy-conscious individuals exploring their own genotype data.

### [DRAFT] Suggested prose

Allelio is an open-source Python tool for privacy-preserving personal genomics analysis.
Users upload raw genotype data from 23andMe, AncestryDNA, or in VCF format, and Allelio
cross-references their genetic variants against two curated public databases: ClinVar, which
catalogues clinically relevant mutations, and the NHGRI-EBI GWAS Catalog, which aggregates
genome-wide association studies. Allelio then generates plain-English explanations of each
finding using a local large language model running via Ollama, with built-in safety guardrails
that prevent the AI from producing definitive medical language. All analysis occurs on the
user's machine — no genomic data is transmitted to external servers. Allelio provides both a
web interface for interactive exploration and a command-line interface for batch processing
and scripted workflows, and outputs shareable HTML reports.

---

## 3. Statement of Need (~250–350 words)

> *JOSS requirement: "A clear Statement of need that illustrates the research purpose of the
> software and places it in the context of related work."*

### Outline of argument

**Paragraph 1 — The problem:**
- Consumer genomics is booming (30M+ people have taken DTC genetic tests).
- Raw data is available for download, but interpreting it requires specialized knowledge.
- Existing interpretation tools fall into two camps:
  (a) Cloud services (Promethease, Nebula Genomics, etc.) that require uploading your genome
      to third-party servers — a serious privacy concern given that genomic data is immutable
      and uniquely identifying.
  (b) Academic bioinformatics pipelines (ANNOVAR, VEP/Ensembl, SnpEff) that require
      institutional infrastructure, command-line expertise, and produce output aimed at
      researchers, not general users.
- There is a gap: no tool offers accessible interpretation with strong privacy guarantees.

**Paragraph 2 — How Allelio fills the gap:**
- Allelio addresses this by combining three capabilities in a single local application:
  1. Multi-format genotype parsing (23andMe, AncestryDNA, VCF)
  2. Automated cross-referencing against ClinVar and GWAS Catalog (downloaded once, ~500 MB)
  3. AI-powered plain-English explanations via a locally-running LLM (Ollama)
- The privacy model is zero-network: after initial database download, Allelio makes no
  outbound connections during analysis.
- The safety layer includes regex-based detection of definitive medical language in LLM
  output, gene-specific warnings for high-impact variants (BRCA1/2, APOE, TP53, Lynch
  syndrome genes), and mandatory disclaimers on every explanation.

**Paragraph 3 — Research applications:**
- Enables privacy-preserving genomics research workflows where data cannot leave the
  researcher's machine (e.g., due to IRB restrictions or institutional policy).
- Provides a platform for studying how local LLMs perform at genomic variant interpretation —
  an open research question in AI-assisted clinical decision support.
- Can serve as a teaching tool in genetics and bioinformatics courses, allowing students
  to explore real variant annotation without cloud dependencies.

### Comparison to existing tools

| Tool | Local? | AI explanations? | Consumer-friendly? | Open source? |
|------|--------|-------------------|---------------------|--------------|
| Promethease | No (cloud) | No | Yes | No |
| ANNOVAR | Yes | No | No (expert) | Free/academic |
| Ensembl VEP | No (web API) | No | No (expert) | Yes |
| OpenSNP | No (cloud) | No | Partially | Yes |
| **Allelio** | **Yes** | **Yes (local LLM)** | **Yes** | **Yes (MIT)** |

> *Note: This table is for your reference during writing. In the final paper, weave the
> comparison into prose rather than using a table — JOSS papers are short and narrative.*

---

## 4. Architecture & Design Decisions (~150–200 words)

> *JOSS doesn't require a formal "Methods" section, but a brief description of key design
> decisions strengthens the paper, especially given the 2026 policy emphasis on
> "irreplaceable human contributions: problem framing, key design decisions, thoughtful
> architectural choices."*

### Points to cover

- **Modular pipeline:** parsers -> database lookup -> analysis/ranking -> AI explanation ->
  report generation. Each stage is independently testable and extensible.
- **Database strategy:** ClinVar and GWAS Catalog are downloaded once and stored locally in
  SQLite via a custom `AllelioDB` class. Batch rsID lookups are optimized for performance.
- **AI safety layer:** A dedicated `safety.py` module implements:
  - Regex-based scanning of LLM output for diagnostic language patterns
    (e.g., "you have," "you will develop," "guaranteed to")
  - Gene-specific warnings for high-impact variants (BRCA1/2, APOE, TP53, MLH1, etc.)
  - Mandatory disclaimers wrapping every explanation
- **Variant ranking:** Clinical significance from ClinVar is converted to a numeric rank
  (pathogenic=1 through benign=10), enabling meaningful sorting and top-N selection.
- **Dual interface:** Flask-based web UI for interactive exploration; Click-based CLI for
  automation and scripting.

---

## 5. Acknowledgements

> *JOSS requirement: "Acknowledgement of any financial support."*

[WRITE] Include:
- Any financial support (or state "This work received no external funding")
- People who contributed but aren't co-authors (e.g., beta testers, advisors)
- Open data sources: "We gratefully acknowledge the National Center for Biotechnology
  Information (NCBI) for ClinVar and the NHGRI-EBI for the GWAS Catalog."
- Ollama project for enabling local LLM inference

---

## 6. References (paper.bib)

> *Create a `paper.bib` file alongside `paper.md` with BibTeX entries for these key
> references.*

### Must-cite references

```
1. ClinVar
   Landrum et al. (2020). "ClinVar: improvements to accessing data."
   Nucleic Acids Research, 48(D1), D835–D844.
   DOI: 10.1093/nar/gkz972

2. GWAS Catalog
   Sollis et al. (2023). "The NHGRI-EBI GWAS Catalog: knowledgebase and
   deposition resource."
   Nucleic Acids Research, 51(D1), D1005–D1012.
   DOI: 10.1093/nar/gkac1010

3. Ollama (software citation)
   [Check for a preferred citation on https://ollama.com or their GitHub]

4. Consumer genomics context / DTC testing
   Regalado (2019). "More than 26 million people have taken an at-home
   ancestry test." MIT Technology Review.
   [Or a more recent peer-reviewed source on DTC testing adoption]

5. Privacy concerns in genomics
   Erlich et al. (2014). "Routes for breaching and protecting genetic privacy."
   Nature Reviews Genetics, 15, 409–421.
   DOI: 10.1038/nrg3723

6. Existing tools for comparison
   - Wang et al. (2010). "ANNOVAR: functional annotation of genetic variants."
     Nucleic Acids Research, 38(16), e164. DOI: 10.1093/nar/gkq603
   - McLaren et al. (2016). "The Ensembl Variant Effect Predictor."
     Genome Biology, 17, 122. DOI: 10.1186/s13059-016-0974-4
```

### [WRITE] Additional references to find
- A recent paper on LLMs for clinical/genomic interpretation (to establish the research
  question of whether local LLMs can perform this task adequately)
- A reference on responsible AI in health contexts

---

## 7. Pre-Submission Checklist

Before submitting, make sure you've addressed these JOSS requirements:

### Software requirements
- [ ] Code is in a public Git repository (GitHub recommended)
- [ ] Repository has been public for **at least 6 months** (2026 JOSS policy)
- [ ] Open source license (MIT — you have this)
- [ ] Issue tracker is public and readable without registration
- [ ] Installation instructions are clear (you have `pip install allelio`)
- [ ] Example usage is documented (you have this in README)

### Documentation requirements
- [ ] Statement of need in the paper
- [ ] Installation instructions in repo
- [ ] Example usage documentation
- [ ] API documentation (docstrings count, but consider generating docs with Sphinx/mkdocs)
- [ ] Community guidelines (CONTRIBUTING.md — consider adding one)

### Testing requirements
- [ ] Automated tests exist (you have `test_analysis.py`, `test_database.py`, `test_parsers.py`)
- [ ] Tests can be run by reviewers after cloning
- [ ] Consider adding CI (GitHub Actions) — JOSS reviewers look for this

### Quality indicators (not required, but strengthen your case)
- [ ] CI/CD pipeline (GitHub Actions running pytest)
- [ ] Code coverage reporting
- [ ] CITATION.cff file in repo
- [ ] A tagged release (e.g., v0.1.0) with a Zenodo DOI archive
- [ ] At least one external contributor or documented user

### 2026-specific requirements
- [ ] Evidence of open development history (public issues, PRs, commits over 6+ months)
- [ ] Evidence of impact or credible near-term significance (benchmarks, tutorial, external
      users, or a reproducible reference analysis)
- [ ] Demonstration of human design contributions (the paper's architecture section covers this)

---

## 8. Critical Path Items — What to Do Before You Can Submit

### Must-do (blockers)

1. **Public repository with 6+ months of history.** JOSS's 2026 policy requires open
   development history. If the repo isn't public yet, make it public now and plan to submit
   no earlier than 6 months after.

2. **ORCID.** Register at https://orcid.org — free, takes 2 minutes.

3. **Reproducible reference analysis.** Create a tutorial or example workflow showing Allelio
   analyzing a well-known reference sample (e.g., NA12878/HG001). This serves as both
   documentation and evidence of credible significance.

4. **paper.bib file.** Compile BibTeX entries for all references listed above.

5. **CITATION.cff.** Add a citation metadata file to the repo so others can cite Allelio.

### Should-do (strengthen submission significantly)

6. **GitHub Actions CI.** Add a workflow running `pytest` on push. Reviewers expect this.

7. **CONTRIBUTING.md.** Brief guide for potential contributors.

8. **Tagged release + Zenodo archive.** JOSS requires an archived version at acceptance;
   setting up the Zenodo-GitHub integration early makes this automatic.

9. **One external validation.** Even one person outside the project confirming they installed
   and ran Allelio successfully adds credibility.

---

## 9. Estimated Word Budget

| Section | Target words | Notes |
|---------|-------------|-------|
| Summary | 100–150 | High-level, non-specialist |
| Statement of Need | 250–350 | Core argument + comparison |
| Architecture | 150–200 | Design decisions, not API docs |
| Acknowledgements | 50–75 | Funding, data sources, thanks |
| **Total** | **~550–775** | Well within 250–1,000 limit |

---

*This outline was prepared based on the [JOSS submission guidelines](https://joss.readthedocs.io/en/latest/submitting.html), the [JOSS paper format](https://joss.readthedocs.io/en/latest/paper.html), and the [2026 scope update](https://blog.joss.theoj.org/2026/01/preparing-joss-for-a-generative-ai-future).*
