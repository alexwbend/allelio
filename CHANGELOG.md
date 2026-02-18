# Changelog

All notable changes to Allelio will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] — 2025-02-16

**Initial public release.** Allelio is a privacy-first, local genomics analysis tool that helps you understand your DNA data without uploading anything to the cloud.

### Added

- **Multi-format genotype parsing** — support for 23andMe (.txt), AncestryDNA (.csv), and VCF (v4.1+) file formats
- **ClinVar database integration** — automatic download, storage, and querying of the NIH's ClinVar variant database for clinical significance lookups
- **GWAS Catalog integration** — download and query the EBI's GWAS Catalog for genome-wide association study results linking variants to traits and conditions
- **Local AI explanations** — plain-English summaries of genetic findings powered by Ollama (local LLM), with no data sent to external servers
- **Web interface** — clean, browser-based UI with drag-and-drop file upload, interactive variant browsing, and one-click HTML report export
- **Command-line interface** — full-featured CLI (`allelio analyze`, `allelio serve`, `allelio setup`) for scripting and automation
- **HTML report generation** — comprehensive, styled reports with variant details, clinical significance, trait associations, and AI explanations
- **Safety guardrails** — medical disclaimers, responsible AI output framing, and clear scope limitations throughout the interface
- **SQLite storage layer** — efficient local database with WAL mode, batch operations, and indexed lookups for fast variant queries
- **One-command setup** — `allelio setup` downloads and indexes ~500 MB of reference data automatically with retry logic
- **Configurable analysis** — control AI model selection, number of variants analyzed, trait-only mode, benign variant inclusion, and more via CLI flags

### Privacy

- Zero network requests during analysis — all processing is local
- No telemetry, tracking, or analytics
- No user accounts or cloud storage
- Genetic data is never persisted by Allelio beyond the analysis session
