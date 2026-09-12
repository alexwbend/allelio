# Changelog

All notable changes to Allelio will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Fixed

- Set aside annotated VCF sites with failed record FILTER or sample FT before
  matching, and report the excluded count separately from negative findings.

- Separate frequency display heuristics from clinical evidence, ignore invalid
  frequency values, and prevent rank caps from increasing benign-row priority.

- Require declared VCF build, chromosome and position agreement with ClinVar
  before counting SNP alleles. Unknown/mismatched identities abstain with a
  reason; no build inference, liftover, or mitochondrial matching is attempted.

- Use structured VCF evidence for ClinVar SNP copy counts, including two
  different alternate alleles at a multiallelic site. VCF reference mismatches
  no longer trigger consumer-array strand inference. Non-SNP VCF records
  remain unknown pending build-aware normalization and cannot enter legacy
  GWAS/PGx matching as flattened SNP genotypes.

- Preserve haploid VCF genotypes as one allele rather than duplicating them,
  so haploid SNVs reach zygosity interpretation with the correct copy count.
- Skip malformed VCF headers without crashing on unset column indices.

### Changed

- ClinVar context survives import and reporting. The importer reads the
  header of `variant_summary.txt` and keeps origin, RCV accessions,
  submitter count, variant type and name, and the separate somatic
  clinical impact and oncogenicity assertions with their review statuses
  and dates; `classification_type` records whether the classification is
  the post-2024 aggregate germline one, from a pre-split file that mixed
  origins, or unknown (legacy database), never assumed. Records are keyed
  by `(rsid, ref, alt, chromosome, allele_id)`, so pseudoautosomal X/Y
  pairs and distinct records for one allele are kept instead of silently
  overwritten (701 such keys in the 2026-09-03 release); the table
  migrates in place without inventing metadata. Every ClinVar entry keeps
  the source classification, its allele match (`allele_match`,
  `allele_match_note`), and Allelio's `display_rank` as separate fields.
  The report, web card, AI prompt, fallback text, and evidence JSON show
  the same context; the prompt is told not to merge records or present a
  somatic assertion as germline. Field mapping in `docs/clinvar-fields.md`,
  with synthetic fixtures in both file layouts.

- Population frequencies are matched by assembly, coordinate, and allele
  before they count. gnomAD rows are keyed by `(rsid, ref, alt)` with
  chromosome, position, assembly, and source version, so the alternate
  alleles of a multiallelic site coexist; a record is labelled `matched`
  only when it agrees with the ClinVar record the genotype matched (or
  declared VCF evidence), and only a matched record may adjust the display
  rank or be described as the person's allele frequency. Other records stay
  visible as context with the reason (`unverified`, `build_mismatch`,
  `position_mismatch`, `other_allele`, `alleles_swapped`,
  `orientation_reversed`); the report, prompt, and evidence JSON say so.
  The extract format gains per-allele rows and an assembly header (format
  2, `scripts/build_gnomad_freq.py`), the build script splits multiallelic
  INFO values per allele instead of keeping the first, and the rsID-only
  table migrates in place. The published format 1 extract now reads as
  unverified context, so the display adjustment is inert until a format 2
  extract is published with its provenance, checksum, and CC0 terms in the
  manifest (`docs/population-frequency.md`).

- Inheritance is resolved for the condition each ClinVar assertion names, not
  for the whole gene: ClinVar's `PhenotypeIDS` identifiers are stored
  (`condition_ids`) and matched to ClinGen curations by MONDO identifier,
  never by name (`mondo-exact` mapping, version 1.0, recorded on every
  resolution). Carrier Status now requires a resolved recessive (or diploid
  X-linked) condition; an assertion naming conditions inherited differently
  reads "conflicting", one without identifiers or naming an uncurated
  condition reads "unresolved" with the reason, and the gene-level summary is
  kept separately. Findings and ClinVar entries carry the full
  `inheritance_resolution` in web payloads and evidence JSON; the CLI table
  shows an Inheritance column. Databases built before the column migrate in
  place and read "identifiers not stored" until `allelio update`. Synthetic
  challenge fixtures cover each path (`docs/inheritance.md`).

### Added

- Gene groups in CLI, web, and HTML reports, with distinct-finding counts,
  source-backed function descriptions where available, and individual details.
  Shared gene associations and unassigned findings remain visible. HTML exports
  no longer truncate at 100 findings, so every gene-summary link is reachable.

- ClinVar assembly, chromosome, VCF position, and source identifiers survive
  parsing, storage, and lookup. Existing allele-aware databases migrate without
  losing rows; missing legacy metadata stays unknown until refresh.

- Optional VCF source evidence on parsed variants: ordered alleles/indices,
  phase and ploidy, raw reference declaration, and quality fields. Existing
  consumer-format constructors remain compatible. See `docs/vcf-evidence.md`
  for interpretation limits and reproducible development checks.

## [0.3.0] - 2026-09-09 — Revival

**Unblocking population frequencies, and hardening the rolling downloads.** The gnomAD frequency feature shipped in 0.2.1 was inert because its data file was never published (the download 404'd). This makes it real and shores up the other data sources against upstream drift.

### Added

- **Pharmacogenomics from ClinPGx.** Setup fetches ClinPGx's (formerly PharmGKB's) clinical annotations bundle (about 1 MB, CC BY-SA 4.0 with a no-selling clause; fetched, never redistributed, not on the permaweb) into a `clinpgx` table keyed by (annotation, genotype). For every annotated site the person's genotype selects its own annotation text, shown under "Pharmacogenomics (ClinPGx)" on the report card and web card with drug, level of evidence, phenotype category and link, and fed to the AI prompt with an instruction never to advise starting, stopping or changing a medication. Only single-rsID annotations are used (star-allele guidance needs phased, copy-number-aware calls an array cannot give) and only levels 1A–2B by default (`pgx_min_level`). A PGx-only site is reported even with no ClinVar or GWAS row. Pharmacogenomic findings are ranked by ClinPGx level (1A/1B with risk factors, 2A/2B a tier below) and are not frequency-downgraded, since a drug-response allele is not a pathogenicity claim. The test suite uses a synthetic fixture in ClinPGx's format.
- **ClinGen gene-disease validity: carrier versus affected.** Setup now fetches ClinGen's gene-validity CSV (about 1 MB, CC0; optional and non-blocking) into a `clingen` table, and every ClinVar-backed finding shows an "Inheritance (ClinGen)" line with the curated conditions and their confidence. One copy of a pathogenic allele in a gene ClinGen curates only for recessive conditions (or on a diploid X for an X-linked one) is now reported under **Carrier Status**, one rank tier below affected genotypes (`CARRIER_RANK_SHIFT`, author choice). Genes with both dominant and recessive curations read "mixed" and are not demoted; only Definitive/Strong/Moderate curations decide. ClinGen is listed in the provenance line, `allelio info`, and the report footer with its file date, as ClinGen asks.
- **A Benign category.** Benign and likely-benign variants used to be filed under "Carrier Status"; they now have their own category in the report, the web tabs, and the CLI, and "Carrier Status" means what it says.
- **Frequency-adjustment ablation.** `scripts/ablation_frequency.py` ranks the example file with the gnomAD adjustment off and on and prints both orderings as a Markdown table (the one in the paper), against the fixture excerpts or, with `--real`, a full local database; `analyze_variants_with_stats(frequency_adjustment=False)` is the switch behind it. Results now sort by (rank, rsID) so the order is identical on every run.
- **A recall test with documented expected findings.** `examples/example_23andme.txt` now has hand-chosen genotypes (0, 1 or 2 copies of each site's annotated allele, a GWAS-only site, benign sites, no-calls, unknown rsIDs, an i-ID row) and `examples/expected_findings.json` says what Allelio must report for each line and why. `tests/test_example_recall.py` builds a database from the real ClinVar / GWAS Catalog / gnomAD rows for those rsIDs (`tests/fixtures/example_*`, extracted by `scripts/build_example_fixtures.py`) and checks every expectation on every push; `scripts/check_example.py` runs the same checks against a full local database for reviewers.
- **ClinVar "drug response" is now Pharmacogenomics.** It was unmatched by the category rules and fell through to Traits or Unknown; it now lands in the Pharmacogenomics category and ranks with risk factors (author choice, documented in `lookup.py`).
- **Zygosity.** Every finding now says how many copies of the annotated allele the person carries: `heterozygous (1 copy of the A allele)`, `homozygous alternate (2 copies…)`, hemizygous on X, or `zygosity unknown` when the source does not name an allele or the genotype matches it on neither strand. It appears on the HTML report card, in the CLI table, in the web result card and its export, and in the AI prompt, which now tells the model that one copy of a recessive variant is carrier status. ClinVar alleles come from its VCF-style columns; GWAS Catalog risk alleles from the "strongest SNP-risk allele" field. Genotypes that only match after complementing are used and flagged "read on the opposite strand" (never at A/T or C/G sites, where a flip is undetectable); 23andMe `I`/`D` indels are matched by length. New module `allelio/analysis/zygosity.py`, pure and tested.
- **A measurable safety filter.** The gate over AI explanations was nine regular expressions, one of which (`you have`) flagged plain statements of genotype ("you have two copies of the risk allele") while missing the sentences that mattered ("you're going to get colon cancer", "stop taking warfarin"). It is now three pattern families, diagnostic / prognostic / prescriptive, that are hedge-aware ("you may have", "does not mean you will develop" pass) and leave statements about the genotype or about risk alone. The Safety Note it appends now names the category it found. A labelled set of 90 sentences (`tests/fixtures/safety_sentences.json`, 45 unsafe including paraphrases written to evade the old filter, 45 safe) is scored by `scripts/safety_eval.py` and pinned by `tests/test_safety.py`: 45/45 caught, 0/45 false positives. The set is author-written and the filter was tuned against it, so this documents the filter's intended scope rather than its performance on arbitrary model output. The prescriptive family is there ahead of the pharmacogenomics work, where "stop taking" is the sentence a model reaches for.
- **Reference-data provenance.** Every database now records which release of ClinVar and the GWAS Catalog it was built from (the release date the server reports at download), the download URL, and the SHA-256 of the exact file, alongside the gnomAD version and checksum already taken from the manifest. `allelio info` shows a release line per source, `allelio analyze` prints the releases before it starts, the HTML report's Data Sources footer names them, and the web status pill and `/api/status` carry the same line. Previously the metadata table stored the literal word "latest", which is not a release: two runs a month apart could differ with nothing in the output to explain why. A `.provenance.json` sidecar beside each downloaded file lets a later run that skips the download still say what it has; a file that predates the sidecar falls back to its own timestamp and is labelled "(from file date)".
- **gnomAD frequency data via a JSON manifest** — the downloader now resolves the compact frequency file through `data/gnomad_manifest.json` (source, version, checksum, and one-or-more URLs) instead of a hardcoded release URL. A version bump or re-host is a data refresh, not a code change. Primary hosting is the permaweb (Arweave via Permavault — content-addressed, never 404s; gnomAD is CC0), with a GitHub release as a mirror.
- **Checksum verification** — a downloaded frequency file is verified against the manifest's SHA-256; a mismatch is rejected and the next URL is tried. A manifest without a checksum downloads but skips the check with a warning rather than blocking.
- **Consumer-array trimming in `scripts/build_gnomad_freq.py`** — a new `--array-sites` option trims the extract to the rsIDs a chip actually reports (23andMe / AncestryDNA), dropping the shipped file from hundreds of MB to a few MB. The script now prints the file's SHA-256 and a ready-to-paste manifest.
- **Staleness banner** — `allelio analyze` and `allelio info` warn when the local ClinVar/GWAS copy is older than 90 days, prompting `allelio update`.
- **Tests** — new coverage for the GWAS URL, staleness logic, manifest resolution, checksum verification, and the array-site trimming.

### Fixed

- **Rows a new ClinVar release no longer carries survived a re-index.** ClinVar and gnomAD rows are replaced by key, never deleted, so a withdrawn record (or a row whose alleles are now read differently) stayed beside the new ones. Both tables are now emptied before re-indexing.
- **Every `allelio setup` or `allelio update` doubled the GWAS table.** GWAS rows are appended (one rsID has many associations, so there is nothing to replace on) and nothing emptied the table first, so a database updated four times held five copies of the catalogue and reported five times the associations. The table is now cleared before each re-index.
- **A ClinVar entry was reported as a finding whether or not the person carried the allele.** Analysis never looked at the genotype: anyone with `rs1800562` on their chip, which is nearly everyone, was shown the HFE hemochromatosis pathogenic entry even when homozygous for the reference G. Positions where the person carries no copy of any annotated allele are now set aside and counted ("N annotated positions where you carry only the reference allele were set aside"), in the CLI, the HTML report, and the web export. `--include-reference` on the analysis API keeps them for inspection.
- **ClinVar's 2024 review-status wording scored zero stars.** "criteria provided, conflicting classifications" (renamed from "…interpretations") was not in the star map, so every conflicting variant lost its one star. Added.
- **GRCh37 lines in ClinVar carried the wrong alleles.** ClinVar lists each allele once per assembly, and the GRCh37 line's VCF-style alleles are not always right (rs6025 reads T/T on GRCh37 and C/T on GRCh38). The parser now makes a first pass to note which alleles have a GRCh38 line and keeps that one.
- **GWAS risk alleles reported on the other strand.** Studies do not always report the risk allele on the forward strand; where ClinVar has given the site's forward-strand alleles, a risk allele that is their complement is now recognised, counted, and flagged "read on the opposite strand" (never at A/T or C/G sites, where the flip is undetectable). All of a site's risk alleles are considered, not just the first row's. A row whose ref equals its alt (a haplotype-level record) is ignored when the same rsID has allele-specific rows.
- **Several ClinVar rows at one rsID collapsed to whichever loaded last.** The table was keyed by rsID alone, so at `rs334` the sickle-cell T>A row and the likely-benign T>G row fought for one slot. The table is now keyed by (rsID, ref, alt) and analysis picks the row for the allele the person carries. This is a schema change: existing databases read as uninitialized until `allelio setup` is run once (it re-indexes the files already on disk).
- **`allelio update` now actually re-downloads.** It only re-indexed whatever was already on disk, because setup skips any source whose file is present, so the "run `allelio update`" advice in the staleness banner never refreshed anything. Update now forces the fetch for every source.
- **Package version string** in `allelio/__init__.py` said 0.2.0 while `pyproject.toml` said 0.2.1; they now agree.
- **The web interface was broken for anyone who installed the package.** `allelio/web/templates/index.html` wasn't declared as package data, so a wheel install shipped without it and every page load of `allelio serve` returned a 500. Invisible from a source checkout, which is why it survived this long. Found by the clean-install smoke test (PUB-4).
- **`python3 -m allelio` now works.** The README offers it as the fallback when the console script isn't on PATH, but the package had no `__main__.py`, so the advice failed with "cannot be directly executed".

### Changed

- **README install instructions match reality.** Allelio isn't on PyPI, so `pip install allelio` never worked; the install section now gives the tested `git+https://` and clone paths, adds the virtual-environment step that recent Pythons require, and states what `allelio setup` actually costs (about 540 MB downloaded, ~2 GB on disk, 15 to 30 minutes) instead of "~500 MB" and "a few minutes".
- **GWAS Catalog download** moved off the retired EBI API v1 endpoint to the versioned FTP path (`releases/latest`), which is release-versioned and stable.
- **gnomAD version pin** bumped v4.1 → v4.1.1. Provenance (source + version) is now stored from the manifest as database metadata (`gnomad_source`, `gnomad_version`) rather than hardcoded, keeping the frequency layer version-agnostic.

---

## [0.2.1] — 2026-02-20

**Population frequency integration.** Allelio now uses gnomAD allele frequency data to distinguish rare pathogenic variants from common ones. A variant flagged "pathogenic" that 40% of the population carries is treated very differently from one carried by 0.01%.

### Added

- **gnomAD population frequency integration** — allele frequencies from the Genome Aggregation Database (gnomAD v4.1) are downloaded during setup and stored locally for offline use
- **Frequency-adjusted significance ranking** — variant significance ranks are now adjusted based on population frequency: common variants (>5% AF) are downgraded significantly, uncommon variants (0.1–1%) receive a small adjustment, and rare variants (<0.1%) retain their original ranking
- **Population frequency display in HTML reports** — variant cards show allele frequency with color-coded labels (Common, Moderate, Uncommon, Rare) plus highest population frequency when different from global
- **Population frequency in AI prompts** — the local LLM now receives gnomAD frequency context alongside clinical data
- **`gnomad` table in SQLite database** — stores rsID, global allele frequency, population-max frequency, allele counts, and population-specific frequencies (AFR, EAS, FIN, NFE, SAS)
- **`GnomADEntry` dataclass** — programmatic access to frequency data on each `VariantResult`
- **`--no-gnomad` flag** for `allelio setup` — skip gnomAD download to save bandwidth
- **Backward compatibility** — existing databases without the gnomad table continue to work
- **29 new tests** covering parser, database, frequency adjustment, analysis integration, and AI prompts

### Changed

- `VariantResult` now includes an optional `gnomad_entry` field
- `AllelioDB.lookup_rsid()` and `lookup_rsids_batch()` now return gnomAD data alongside ClinVar and GWAS
- `AllelioDB.get_stats()` now includes `gnomad_entries` count
- `setup_database()` accepts `include_gnomad` parameter (default: True)
- AI prompt template now includes a "Population Frequency (gnomAD)" section
- Report footer lists gnomAD as a data source

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
