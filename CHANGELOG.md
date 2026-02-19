# Changelog

All notable changes to Allelio will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.0] — 2026-02-19

**Smarter ranking & redesigned reports.** Allelio now uses ClinVar's review star ratings (0–4 stars) to weight variant significance scores, and HTML reports have been reorganized with section reordering and tab navigation.

### Added

- **Review star ratings** — ClinVar review statuses are mapped to a 0–4 star scale matching ClinVar's own review system (practice guideline = 4★, expert panel = 3★, multiple submitters = 2★, single submitter = 1★, no assertion = 0★)
- **Weighted significance ranking** — variant significance scores are now adjusted by review quality (up to 0.4 points), so better-reviewed variants sort higher within the same significance tier without crossing tier boundaries
- **Review quality display in HTML reports** — variant cards now show a visual star rating (★★★☆) with color-coded indicators (green for 3–4 stars, amber for 1–2, gray for 0); row is hidden on GWAS-only cards
- **Review quality in AI prompts** — the local LLM now receives star ratings alongside review status text, enabling more nuanced explanations that account for evidence quality
- **Tab navigation bar** — sticky navigation at the top of HTML reports with anchor links to each section, variant count badges, and color-coded tabs; only sections with results are shown; hidden in print mode
- **`review_stars` field on ClinVarEntry** — programmatic access to the computed star rating for each ClinVar entry
- **`_get_review_stars()` helper** — public utility function for converting ClinVar review status strings to star ratings
- **`REVIEW_STATUS_STARS` mapping** — exported constant mapping all known ClinVar review statuses to their star values

### Changed

- **Report section order** — sections are now ordered by clinical actionability: Health Conditions → Risk Factors → Pharmacogenomics → Traits → Carrier Status (was alphabetical)
- `VariantResult.significance_rank` is now a `float` (was `int`) to accommodate fractional weighting by review quality

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
