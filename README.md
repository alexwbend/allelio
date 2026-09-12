# Allelio

[![Tests](https://github.com/alexwbend/allelio/actions/workflows/tests.yml/badge.svg)](https://github.com/alexwbend/allelio/actions/workflows/tests.yml)

**Explore genetic variants locally, with traceable annotations, gene-level views, and optional AI explanations.**

Allelio is open-source software for inspecting variants from 23andMe,
AncestryDNA and supported VCF files. It brings together local reference data
from ClinVar, GWAS Catalog, gnomAD, ClinGen and ClinPGx, groups findings by gene,
and produces browsable HTML reports. A local language model can explain the
retrieved evidence in plain language; annotation also works without AI.

The project is in **alpha**, for research and education. It does not diagnose
disease, perform comprehensive genetic testing, or establish treatment
recommendations. A source classification, an allele match and an AI explanation
are different kinds of information; none alone establishes a person's health
status. Discuss health-related findings with a qualified professional.

[Quick start](#quick-start) · [Capabilities](#what-you-can-do) ·
[Supported scope](#supported-inputs-and-interpretation-limits) ·
[Privacy](#privacy-and-local-data) · [Verification](#development-and-verification)

## What you can do

- **Inspect source evidence.** View classifications, associations, review status,
  available inheritance context and genotype-specific drug-response annotations.
- **See how an allele was matched.** Supported ClinVar VCF SNP matching checks
  declared build, chromosome, position and alleles. Unsupported cases remain
  unknown; explicit failed VCF filters are set aside and counted.
- **Browse findings by gene.** Expand groups while retaining individual findings,
  categories and source links. A small versioned catalogue supplies sourced gene
  function summaries where available.
- **Use optional local explanations.** Connect Ollama or a local
  OpenAI-compatible server. Each explanation records its model attribution;
  source-based fallback text remains available when generation fails.
- **Save and inspect reports.** CLI and web HTML exports retain returned
  findings beyond the top-N explanation limit. Web analyses can be explicitly
  saved on your computer and reopened.
- **Track reference releases.** Setup records source metadata and checksums;
  the CLI and reports show available release information.

Allelio is useful for researchers testing annotation workflows, students
learning how genomic evidence is represented, and people exploring their own
raw data with its limitations in view. It is not a replacement for clinical
variant interpretation or genetic counseling.

## Quick start

### Install from the repository

Use Python 3.9 or later. CI currently checks Python 3.9–3.12.

```bash
git clone https://github.com/alexwbend/allelio.git
cd allelio
python3 -m venv .venv
source .venv/bin/activate
pip install .
allelio --version
```

On Windows, use `.venv\Scripts\activate` to activate the environment. Activate
it again in each new terminal. A checkout includes the synthetic examples,
documentation and development checks.

### Download reference data

```bash
allelio setup
allelio info
```

Setup downloads reference files and builds a local database under
`~/.allelio/data`. Allow several gigabytes of disk space; download size and
setup time depend on the source releases and your connection. Reference setup
and model downloads require internet access. To refresh the reference data:

```bash
allelio update
```

Updating can change findings. Record the releases used when comparing runs.
Older databases may lack source identity fields or release metadata; refresh
before relying on the newer VCF identity checks.

### Try the synthetic example without AI

```bash
allelio analyze examples/example_23andme.txt --no-ai --output example_report.html
```

The [example guide](examples/README.md) explains the synthetic input and its
expected findings. These are software checks, not clinical validation data.

### Use the web interface

```bash
allelio serve
```

Open [http://localhost:8080](http://localhost:8080), select your file, and browse
the results. The upload goes to the local Allelio process. See
[Privacy and local data](#privacy-and-local-data) for temporary files, optional
saving and the model-server boundary.

### Add a local model, if desired

Install [Ollama](https://ollama.com), then download a model:

```bash
ollama pull llama3.1:8b
allelio analyze examples/example_23andme.txt --output example_with_explanations.html
```

This is the default model configuration, not a validated recommendation for
clinical interpretation. Memory use and generation time depend on the model,
quantization, runtime and hardware. See [local model setup](docs/local-models.md).

Useful CLI options:

```bash
# Explain and show the top 50 findings in the summary table
allelio analyze my_data.txt --top 50 --output my_report.html

# Keep annotation and reporting, without model generation
allelio analyze my_data.txt --no-ai

# Choose a model installed on your local server
allelio analyze my_data.txt --model mistral-nemo:12b

# Restrict the displayed results to trait associations
allelio analyze my_data.txt --traits-only
```

`--top` limits the top-results table and requested explanations, not the
complete gene summary or returned findings in the HTML report. Category and
analysis filters still affect which findings are returned.

## Reference evidence

| Source | Used for | Interpretation boundary |
|---|---|---|
| [ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/) | Submitted variant classifications, conditions, review status and allele identifiers | Assertions can disagree or change; retrieval is not independent verification |
| [GWAS Catalog](https://www.ebi.ac.uk/gwas/) | Variant–trait associations and reported risk alleles | An association is not a personal risk estimate or a causal diagnosis |
| [gnomAD](https://gnomad.broadinstitute.org/) | Population-frequency context from a pinned compact extract | Coverage is incomplete; rarity and commonness alone do not classify a variant |
| [ClinGen](https://clinicalgenome.org/) | Gene–disease validity and inheritance context | Current gene-level rules do not resolve every allele–condition relationship |
| [ClinPGx](https://www.clinpgx.org/) | Supported single-rsID, genotype-specific pharmacogenomic annotations | No comprehensive star-allele, diplotype or metabolizer calling |

Source records and an optional display ranking are separate. Allelio does not
perform a complete ACMG/AMP classification. ClinVar itself distinguishes
[germline, oncogenicity and somatic clinical-impact classifications](https://doi.org/10.1093/nar/gkae1090);
Allelio should not be treated as a general somatic interpretation pipeline.

### Reference versions and storage

ClinVar, GWAS Catalog, ClinGen and ClinPGx are downloaded from their configured
source endpoints. The compact gnomAD extract is pinned through
[`data/gnomad_manifest.json`](data/gnomad_manifest.json), with a checksum and
Arweave/GitHub mirror locations. Downloads are checked against the manifest's
SHA-256. Hosting provides redundancy, not a guarantee of perpetual availability
or biological accuracy. See [`scripts/build_gnomad_freq.py`](scripts/build_gnomad_freq.py)
for the extract-building workflow.

Available source release dates, URLs and file checksums are recorded during
setup. `allelio info` shows reference information, and reports include source
context. Missing metadata is reported as unknown. These records help explain
changes between runs; they are not yet a complete environment or model manifest.
Reference datasets have their own terms, separate from Allelio's code license.

## Supported inputs and interpretation limits

| Input | Supported handling | Main limits |
|---|---|---|
| 23andMe tab-delimited raw text | rsID, chromosome, position and genotype parsing | Internal `i` probe IDs are not resolved; array coverage is incomplete |
| AncestryDNA tab-delimited raw text | rsID and allele-column parsing | The file layout matters, not its `.txt` or `.csv` extension; arbitrary CSV is not supported |
| VCF | rsID-based records, explicit alleles and genotype evidence; haploid/diploid calls | First sample only; no general liftover, sequence normalization or comprehensive structural-variant interpretation |

The parsers also accept gzip-compressed files. VCF records without usable rsIDs,
no-calls, partial calls and unsupported genotype encodings can be skipped; the
current report is not a complete audit of every input row. “No reported finding”
does not distinguish every possible coverage or evidence gap and must not be
read as a negative genetic test.

### VCF identity and quality

For ClinVar SNP copy counts, recognized declared builds (`GRCh37`/`hg19` and
`GRCh38`/`hg38`) must agree with the source build and coordinates. Alleles must
also match. Filenames and URLs are not guessed into builds. Mitochondrial
reference equivalence and general indel normalization are not supported.
Unknown or mismatched identity remains an unknown interpretation. These checks
do not authenticate the declared reference sequence and do not establish
universal build-aware matching for every source.

Record `FILTER` or sample `FORMAT/FT` failures exclude an annotated VCF site
before ClinVar, GWAS or PGx matching. CLI, web and HTML reports show the excluded
count separately. `PASS` records passed upstream filters; missing or unapplied
filters remain unknown and do not themselves exclude a site. Allelio does not
invent QUAL/GQ/DP cutoffs. See the [VCF specification](https://samtools.github.io/hts-specs/VCFv4.3.pdf).

### Allele counts and inheritance

Where supported, findings show the number of copies of an annotated allele.
Known non-carried ClinVar alleles are set aside; unresolved matches remain
unknown. Consumer-array matching includes limited strand-complement and `I`/`D`
length handling, which is not sequence-level confirmation of an indel. VCF SNP
matching does not use that strand inference.

ClinGen curations provide inheritance context. Current rules can group a
single-copy finding under **Carrier Status** for a gene with suitable recessive
curations; mixed inheritance remains unresolved. These are gene-level
presentation rules, not condition-specific diagnoses. Haploid or diploid allele
counts do not establish biological sex, penetrance, symptoms or affected status.

### Gene grouping

Groups use unambiguous source HGNC identifiers where available and gene symbols
otherwise. Shared findings can appear in more than one group, so group counts
must not be summed into a total number of variants. Unassigned findings remain
visible. Multiple findings do not establish combined risk, a haplotype or
compound heterozygosity.

The offline function catalogue currently covers BRCA1, BRCA2, CFTR, APOE and HFE
with sourced summaries; other genes have an explicit missing-summary fallback.
See [gene grouping](docs/gene-grouping.md) for identifiers, counting rules and
saved-report compatibility.

### Pharmacogenomics

Allelio matches supported single-rsID ClinPGx annotations to a recorded genotype,
using evidence levels 1A–2B by default. It does not reconstruct star alleles,
phase multiple sites, resolve copy-number variation or recommend medication
changes. A missing annotation is not evidence of normal drug metabolism.
Drug-response findings do not receive the optional frequency ranking penalty.

### Display ranking

`significance_rank` determines display priority, not disease probability. It
starts from source classifications, with review-status adjustments and an
optional frequency heuristic. The 5%, 1% and 0.1% frequency tiers and their
penalties are software choices, not ACMG/AMP evidence rules. Invalid frequencies
do not adjust ranking; the cap cannot promote an already-benign row.

[BS1 is relative to a disorder's expected allele frequency](https://dataexchange.clinicalgenome.org/interpretation/entities/VariantPathogenicityInterpretationCriterion.html),
not a universal 1% cutoff. Source classifications remain unchanged by ranking.
Explore the current heuristic on the example with:

```bash
python3 scripts/ablation_frequency.py
```

## Using a different local model

For a local server implementing an OpenAI-compatible API:

```bash
export ALLELIO_OPENAI_BASE=http://127.0.0.1:1234/v1
export ALLELIO_MODEL=your-local-model-name
allelio analyze my_data.txt
```

Include `/v1`. If the server lists exactly one model, Allelio can use its name;
servers exposing multiple models require an explicit choice. The web interface
and `allelio info` show available model status. Reports distinguish model-written
explanations from source-based fallback text.

### Explanation checks

Generated text passes through a lexical filter for certain unhedged diagnostic,
prognostic and prescriptive language. Flagged text receives a visible note.
The filter does not verify factual correctness, detect all hallucinations or
measure whether important information was omitted. Its author-written sentence
fixtures are development evidence, not independent clinical evaluation.

```bash
python3 scripts/safety_eval.py
```

## Privacy and local data

- **Local annotation:** reference lookups use the local database after setup.
  No account is required to use Allelio, and the application has no telemetry.
- **Local model endpoints:** Allelio restricts model connections to loopback,
  ignores environment proxies for those requests, and rejects recognized Ollama
  cloud-model names. Prompts contain variant information.
- **A separate server boundary:** a local proxy or model daemon could forward
  requests elsewhere. Allelio cannot prove what another process does. Configure
  and inspect that server separately; endpoint checks are not a complete
  network-isolation guarantee.
- **Actual network activity:** setup/update and model downloads access remote
  services. The web interface and model client use local HTTP. Clicking report
  links opens external sites and can disclose the variant or gene in the URL.
- **Local files:** web uploads use a temporary file, removed during normal
  request cleanup. Crashes can leave temporary artifacts. Explicitly saved web
  results persist at `~/.allelio/last_analysis.json`; HTML reports persist where
  you save them. These files contain genetic information and are not encrypted
  by Allelio. Reference databases also remain on disk.

Keep the web service on its default local interface. Review saved files,
backups, browser behavior and model-server settings before working with
sensitive data. `--no-ai` avoids model-generation requests; it does not remove
existing saved reports.

## Development and verification

From a checkout, activate your virtual environment and install development
dependencies. Node.js is also required for the JavaScript rendering checks.

```bash
pip install -e '.[dev]'
python3 -m pytest -q
python3 scripts/publication_baseline.py --output /tmp/allelio-baseline.json
```

The baseline uses shipped fixtures and a temporary database, without model
inference or live reference downloads. Its JSON records the source revision,
working-tree status, hashes and check outcomes. The test suite covers parsers,
matching, abstention, reporting and local-server restrictions. External services
are mocked in these tests; they do not constitute an operating-system-level
network audit. Neither passing tests nor matching a reference database establishes
clinical validity or independent replication.

For an example check against your own built reference database:

```bash
python3 scripts/check_example.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow and
[GitHub issues](https://github.com/alexwbend/allelio/issues) for current public
work. Useful contributions include minimal synthetic failure cases, source
format compatibility, coverage accounting and reproducible comparisons.
Please do not post personal genotype files in issues.

## Troubleshooting

- **Command unavailable:** activate the virtual environment and run
  `allelio --version` to verify installation.
- **Reference download failed:** check connectivity and retry `allelio setup`.
- **Old or unknown source metadata:** run `allelio update`, then `allelio info`.
- **Model unavailable:** start your local server and confirm the configured model
  is installed. Use `--no-ai` to run annotation without generation.
- **Slow analysis:** distinguish reference setup, annotation and generation.
  Generation time depends on the model and hardware; `--top` limits requested
  explanations and `--no-ai` skips them.

## Contributing, citation and license

Contributions follow [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md). Cite the software using
[CITATION.cff](CITATION.cff), and record the software and reference versions used.

Allelio's code is [MIT licensed](LICENSE). Reference data and model weights
retain their respective licenses and terms. The software is provided as-is
for research and education, without a claim of clinical validation.

Structured evidence is available with `allelio analyze input.txt --no-ai
--json-output evidence.json` or **Export Evidence JSON** in the web report.
See the [versioned export contract](docs/evidence-export.md) for retained source
fields, input evidence, and interpretation limits.
