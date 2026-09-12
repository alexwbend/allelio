# Allelio

[![Tests](https://github.com/alexwbend/allelio/actions/workflows/tests.yml/badge.svg)](https://github.com/alexwbend/allelio/actions/workflows/tests.yml)

**Understand your DNA — privately, on your own computer.**

Allelio is a free, open-source tool that analyzes your raw genetic data from services like 23andMe or AncestryDNA. It tells you what your genetic variants mean by cross-referencing them against trusted scientific databases — and it explains everything in plain English using AI.

The key difference? **Everything happens locally on your machine.** Your genetic data never leaves your computer. No cloud uploads, no tracking, no accounts.

---

## Who is this for?

- **Curious individuals** who got their DNA tested and want to understand what the results actually mean
- **Privacy-conscious people** who don't want their genetic data sitting on someone else's server
- **Researchers and students** exploring genomics with real data
- **Developers** interested in bioinformatics and local AI applications

No programming experience is needed to use Allelio's web interface — just upload your file and browse your results.

---

## What does it do?

1. **Reads your DNA file** — supports 23andMe (.txt), AncestryDNA (.csv), and VCF formats
2. **Looks up your variants** in five public scientific databases:
   - [ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/) — clinically significant genetic variants curated by the NIH
   - [GWAS Catalog](https://www.ebi.ac.uk/gwas/) — genome-wide association studies linking variants to traits and conditions
   - [gnomAD](https://gnomad.broadinstitute.org/): how common each variant is in the population, so common ones rank lower
   - [ClinGen](https://clinicalgenome.org/): how each gene-disease link is inherited and how well established it is, so one copy of a recessive variant is reported as carrier status
   - [ClinPGx](https://www.clinpgx.org/) (formerly PharmGKB): how variants affect response to specific drugs, with the annotation written for your exact genotype
3. **Explains findings in plain English** using a local AI model — Ollama, or any OpenAI-compatible server you already run — so you don't need a genetics degree to understand the results
4. **Generates a report** you can save, print, or share with your doctor

All of this runs entirely on your computer. Nothing is uploaded anywhere.

---

## 🚨 Important: This is not medical advice

**Allelio is an educational and research tool — not a diagnostic instrument.** Genetic findings can be complex and context-dependent. A variant that sounds scary might be completely normal in your population, and vice versa.

**Before making any health decisions based on genetic information:**
- Talk to your doctor or a genetic counselor
- Don't self-diagnose based on what you see here
- Remember that risk factors are statistical associations, not certainties

We take this seriously, and you'll see reminders throughout the tool.

---

## Getting started

### What you'll need

- **Python 3.9 or later** — [download here](https://www.python.org/downloads/) if you don't have it
- **Your raw DNA data file** from 23andMe, AncestryDNA, or in VCF format
- **Ollama** (optional but recommended) — this runs the AI that explains your results in plain English
  - [Download Ollama](https://ollama.com) and install it
  - Then open a terminal and run: `ollama pull llama3.1:8b` (downloads a ~4 GB model)
  - If you skip this, Allelio still works — you just won't get AI-written explanations
  - Already running something else? See [Using a different local model](#using-a-different-local-model)

### Install Allelio

Allelio isn't on PyPI yet, so you install it from GitHub. Open a terminal
(Terminal on Mac, Command Prompt or PowerShell on Windows) and run:

```bash
python3 -m venv allelio-env
source allelio-env/bin/activate    # Windows: allelio-env\Scripts\activate
pip install git+https://github.com/alexwbend/allelio.git
```

The virtual environment isn't optional bureaucracy: recent Pythons (Homebrew,
Debian, Ubuntu) refuse a plain `pip install` outside one with an
`externally-managed-environment` error. You'll need to `activate` it again in
each new terminal before running `allelio`.

Prefer a checkout, so you also get the example file, the tests, and the paper?

```bash
git clone https://github.com/alexwbend/allelio.git
cd allelio
python3 -m venv .venv && source .venv/bin/activate
pip install .
```

Check it landed:

```bash
allelio --version
```

### Set up the databases (one time only)

This downloads the ClinVar and GWAS reference databases and builds a local
index. You only need to do this once:

```bash
allelio setup
```

Setup also fetches a small gnomAD allele-frequency file (about 24 MB) that lets
Allelio downgrade common variants so genuinely rare findings stand out. See
[Where the reference data lives](#where-the-reference-data-lives) below for how
that file is hosted.

**What it costs you.** About 540 MB downloaded (ClinVar ~440 MB, GWAS ~70 MB
compressed, gnomAD ~24 MB) and roughly **2 GB left on disk** under
`~/.allelio/data`: the built database plus the raw downloads, which Allelio
keeps so `allelio update` doesn't have to re-fetch what hasn't changed. Budget
15 to 30 minutes, and more if NIH's FTP is having a slow day; it's one long
wait, not a hung command, and it prints progress every 10%. Run it once and you
never wait again.

### Launch the web interface

```bash
allelio serve
```

Then open your browser to **http://localhost:8080**. You'll see a clean interface where you can upload your DNA file, browse your variants, read AI explanations, and export a full report.

### Or use the command line

Don't have a DNA file handy? [`examples/`](examples/) has a small synthetic
one you can run right away, with a file that says exactly what Allelio must
find in it (`examples/expected_findings.json`, checked by the test suite and
by `python3 scripts/check_example.py` against your own database), see
[`examples/README.md`](examples/README.md). If you installed straight from
GitHub rather than cloning, grab just that file:

```bash
curl -O https://raw.githubusercontent.com/alexwbend/allelio/main/examples/example_23andme.txt
```

If you prefer the terminal:

```bash
# Basic analysis with AI explanations for top 20 variants
allelio analyze my_23andme_data.txt

# Save the report to a file
allelio analyze my_23andme_data.txt --output my_report.html

# Analyze more variants (top 50 instead of default 20)
allelio analyze my_23andme_data.txt --top 50

# Skip AI explanations for faster results
allelio analyze my_23andme_data.txt --no-ai

# Name the model to explain with
allelio analyze my_23andme_data.txt --model mistral-nemo:12b

# Only show trait associations (no disease risks)
allelio analyze my_23andme_data.txt --traits-only
```

---

## Using a different local model

Ollama is the default, not the requirement. If you already run a model server
that speaks the OpenAI API — llama.cpp, LM Studio, vLLM, llama-swap — point
Allelio at it:

```bash
# LM Studio
export ALLELIO_OPENAI_BASE=http://127.0.0.1:1234/v1

# llama.cpp --server, naming the model explicitly
export ALLELIO_OPENAI_BASE=http://127.0.0.1:8080/v1
export ALLELIO_MODEL=qwen2.5-14b-instruct
```

Include the `/v1` — that is the part servers disagree about. If you don't set
`ALLELIO_MODEL`, Allelio asks the server what it is serving, and uses that name
when the answer is a single model. Servers that keep a dozen configured — a
llama-swap config, say — need `ALLELIO_MODEL`, because there is nothing to
infer; the alias from your llama-swap config works there, not just the full
model id. If the server lists what it serves and the name you gave is not
in that list, Allelio says so, skips the explanations and writes the report
anyway — the findings never needed a model, and no name is put on someone
else's answers. A server that will not list its models at all, like a bare
`llama.cpp`, is simply asked; if it has not got that model it says so, and
again nothing is credited. `ALLELIO_MODEL` works with plain Ollama too.

Whichever you use, the web interface and `allelio info` both print the model
that is actually answering, and every explanation says who wrote it — the model
by name, or nobody, in which case the card is the variant's own ClinVar and
GWAS Catalog data and says so. A run where the model answers for some variants
and not others is reported as exactly that, on the page and in the report.

**The address has to be on your machine.** `127.0.0.1`, `::1` or a name that
resolves to one of them — anything else is refused, with the reason, before any analysis starts.
This is not a configuration preference: every prompt Allelio sends contains the
variant it is asking about, so a hosted endpoint in that setting would be
reading your genome. There is deliberately no way to send an API key, and no
proxy is used even if one is configured for the rest of your system.

Ollama's `-cloud` models are the exception the address check cannot see: the
request goes to `127.0.0.1:11434` and the Ollama daemon forwards it to
ollama.com. Allelio refuses those by name. Anything you have pulled locally is
fine.

New to running a model locally? The [Running a local model well](docs/local-models.md)
guide covers how to be sure your data stayed on your machine, which model to
pick for your RAM, and what a good setup feels like.

---

## Supported file formats

| Format | Source | How to get your file |
|--------|--------|---------------------|
| .txt | 23andMe | Account → Settings → 23andMe Data → Download Raw Data |
| .csv | AncestryDNA | Settings → Download DNA Data |
| .vcf | Various | Standard variant call format (v4.1+) from clinical or research sequencing |

---

## Findings by gene

Results now include gene groups in the CLI, web interface, and HTML reports.
Expand a group to inspect its findings, their categories, and any available
sourced function summary. Shared findings can appear under several genes; having
multiple findings alone does not establish higher risk. See
[gene grouping](docs/gene-grouping.md) for counting rules and coverage limits.

## How it works under the hood

Allelio's pipeline is straightforward:

1. **Parse** — reads your genotype file and extracts your genetic variants (SNPs)
2. **Lookup** — checks each variant against the local ClinVar and GWAS databases
3. **Analyze** — gathers clinical significance, associated traits, and biological context
4. **Explain** — sends the findings to your local AI model for plain-English summaries
5. **Check**: runs each explanation through a safety filter before you see it (below)
6. **Present**: displays results in your browser or exports them as an HTML report

The reference databases are stored locally on your machine after the initial download. During analysis, Allelio makes **zero network requests** — your data stays put.

### The safety filter on AI explanations

A local language model can write a confident sentence that no genetics
professional would write. Allelio does not trust the model's tone, so every
explanation passes through a lexical safety filter (`allelio/ai/safety.py`)
before it reaches you. It flags three kinds of unhedged, second-person
language and appends a visible Safety Note naming which kind it found:

- **diagnostic**: "you have Lynch syndrome", "this confirms that you have…"
- **prognostic**: "you will develop…", "guaranteed to…", "100% chance…"
- **prescriptive**: "stop taking warfarin", "double your dose"

It is built to leave the language the prompt asks for alone: hedged statements
("you may have a higher risk"), population-level ones ("carriers have…"), and
plain facts about your genotype ("you have two copies of the risk allele")
pass through. The filter is a set of patterns, not a judge of accuracy. It
cannot tell you whether an explanation is *correct*, and a determined
paraphrase can get past it. Its scope is measured against a labelled set of
90 sentences in `tests/fixtures/safety_sentences.json` (45 that should be
flagged, 45 that should not); `python3 scripts/safety_eval.py` prints the
catch rate and false-positive rate, and the test suite fails if either
regresses. The set was written by the author and the filter tuned against it,
so treat the numbers as a statement of intended scope rather than of how it
fares on arbitrary model output.

### Knowing which data you ran against

ClinVar and the GWAS Catalog are rolling releases, so the same DNA file can
produce different findings a month apart. To keep every result reproducible,
Allelio records at setup **which release of each source it was built from**
(the release date the server reports for ClinVar and GWAS, the creation date
ClinGen and ClinPGx stamp into their files, the pinned version for gnomAD), the download
URL, and the SHA-256 checksum of the exact file. You
see this in three places:

- `allelio info` lists a release line per source with its checksum
- `allelio analyze` prints the reference releases before it starts, and the
  HTML report's **Data Sources** footer repeats them
- the web interface's status pill and its `/api/status` endpoint carry the
  same line

If a release shows as `unknown`, the database predates this feature; run
`allelio update` once and it will be filled in. `allelio update` now genuinely
re-downloads every source (it used to only re-index the copies already on
disk), so a refresh moves the release dates forward.

---

## Which allele you carry: zygosity

A database entry describes one allele at one position. Your file says which
two alleles you have there. Allelio matches the two before it reports anything,
because the same ClinVar row means three different things depending on the
match:

- **no copies** of the annotated allele (homozygous reference): the entry does
  not apply to you. It is **not a finding** and is not listed. The report and
  the CLI say how many such positions were set aside, so the omission is
  visible rather than silent.
- **one copy** (heterozygous): for a condition inherited recessively this is
  carrier status; for a dominant one it is the affected genotype.
- **two copies** (homozygous alternate), or one copy on the X chromosome in a
  male (hemizygous): the affected genotype for a recessive condition.

Every finding shows its zygosity next to the genotype, e.g.
`heterozygous (1 copy of the A allele)`, and the AI prompt carries the same
phrase so the explanation can say carrier when it means carrier. ClinVar
alleles are read from its VCF-style columns and GWAS Catalog risk alleles from
the "strongest SNP-risk allele" field. Both are on the forward strand of the
reference build, as consumer files are; if a genotype only matches after
complementing it, and the site is not an A/T or C/G one where a flip cannot be
detected, Allelio uses the complement and marks the call "read on the opposite
strand". 23andMe's `I`/`D` indel notation is matched by allele length.

Two things follow from this that earlier versions got wrong. ClinVar can
carry several rows for one rsID, one per alternate allele, with different
classifications (at `rs334`, T>A is sickle-cell disease and T>G is likely
benign); Allelio now keeps every row and reports the one for the allele you
actually carry. And a pathogenic entry at a position where you carry only the
reference allele used to be reported as a finding; it no longer is.

When the source does not name an allele (ClinVar writes `na` for some large or
complex variants; some GWAS studies report `?`), or your genotype matches it on
neither strand, the finding is still listed but marked **zygosity unknown**,
and the report counts those too.

### Carrier or affected: inheritance from ClinGen

Knowing you carry one copy is only half the story; whether one copy matters
depends on how the condition is inherited. Allelio takes that from
[ClinGen's gene-disease validity](https://search.clinicalgenome.org/kb/gene-validity)
curations (a small CC0 file fetched at setup), which give each established
gene-disease relationship a mode of inheritance and a confidence level. Every
ClinVar-backed finding shows an **Inheritance (ClinGen)** line, and the rule
is deliberately narrow:

- **one copy** of a pathogenic allele in a gene ClinGen curates **only for
  recessive conditions** (or one copy on a diploid X for an X-linked one) is
  reported under **Carrier Status** and ordered one tier below affected
  genotypes (an author choice, documented in `lookup.py`);
- **two copies** in such a gene, or one copy where the gene has a dominant
  curation, stays under **Health Conditions**;
- a gene curated for **both** dominant and recessive conditions (HBB, GBA1,
  BRCA1) reads "mixed" and is **not** demoted, because gene-level curation
  cannot say which condition your allele causes; the note names the
  conditions so you and the model can reason about it;
- only Definitive, Strong and Moderate curations decide inheritance; a gene
  with none reads "not curated" and nothing changes.

"Carrier Status" used to be where benign variants landed. They now have their
own **Benign** category.

### Pharmacogenomics from ClinPGx

[ClinPGx](https://www.clinpgx.org/) (the successor to PharmGKB, which now
also houses CPIC and PharmCAT) publishes clinical annotations: for a variant
and a drug, a level of evidence and, for each genotype, a sentence saying
what people with that genotype can expect. Allelio fetches the bundle at
setup (about 1 MB) and, for every site in your file it annotates, shows the
annotation written for **your** genotype under **Pharmacogenomics
(ClinPGx)**, with the drug, the level, the phenotype category (dosage,
efficacy, toxicity, metabolism) and a link. The same text goes into the AI
prompt, which is told to explain it and never to advise starting, stopping
or changing a medication; the safety filter's prescriptive family backs that
up.

Three deliberate limits:

- **Single-rsID annotations only.** Most CYP2D6, CYP2C19 and DPYD guidance is
  written against star alleles (`CYP2D6*4`), which need phased haplotypes
  and copy-number calls a consumer array does not provide. Those annotations
  are skipped rather than guessed at, which is why a DPYD site can show
  ClinVar's "drug response" and no ClinPGx note.
- **Evidence levels 1A–2B by default.** Level 3 (single or conflicting
  studies) has thousands of annotations and would bury everything else;
  `analyze_variants_with_stats(pgx_min_level="3")` includes them.
- **No frequency downgrade.** The gnomAD adjustment says "a common allele is
  unlikely to be pathogenic", which is beside the point for a drug-response
  allele; pharmacogenomic findings are ranked by ClinPGx level alone
  (1A/1B with risk factors, 2A/2B a tier below).

ClinPGx data is **CC BY-SA 4.0 with a no-selling clause**. Allelio downloads
it to your machine and never redistributes it (it is not on the permaweb, and
the test suite uses a synthetic fixture in the same format); the report
credits ClinPGx and PharmGKB with the file date.

**Upgrading from 0.2.x:** the ClinVar table changed shape to hold one row per
allele, and ClinGen is a new download. Run `allelio setup` once (it re-indexes the files already on disk, no
re-download) and `allelio info` will show the database as initialized again.

---

## How variants are ranked

Allelio sorts findings by a `significance_rank` (lower = shown first). This is
a **prioritization heuristic for presentation order, not a validated clinical
or diagnostic score** — it is meant to surface the findings most worth a
closer look, nothing more.

The rank starts from ClinVar's clinical significance (pathogenic ranks
highest, then likely pathogenic, then risk factor and drug response together,
then association, and so on down to benign), then two adjustments are applied:

1. **Review quality.** ClinVar's [review-status star
   system](https://www.ncbi.nlm.nih.gov/clinvar/docs/review_status/) (0–4
   stars) nudges the rank within its own tier — a 4-star pathogenic call
   ranks slightly above a 0-star one — capped so it can never cross into a
   different significance tier.
2. **Population frequency.** A variant common in gnomAD is less likely to be
   truly pathogenic, so common variants (allele frequency above roughly 5%
   and 1%, echoing the [ACMG/AMP BA1 and BS1 population-frequency
   thresholds](https://doi.org/10.1038/gim.2015.30), Richards et al. 2015) are
   downgraded toward "less significant," capped so they never fully cross the
   benign boundary.

To see exactly what the frequency adjustment does, run
`python3 scripts/ablation_frequency.py`: it ranks the example file with the
adjustment off and on and prints both orderings side by side (add `--real`
to use your full local database). On the example, the adjustment leaves the
rare pathogenic alleles where they are and pushes two common
"conflicting" variants (APOE ε4, HFE H63D) below the default cutoff.

The frequency *thresholds* are cited to ACMG/AMP; the specific *penalty
sizes* are not — ACMG/AMP's BA1/BS1 are qualitative evidence codes, not point
values, so Allelio's amounts are an author choice, documented as such at each
constant in `allelio/analysis/lookup.py`.

---

## Known gaps: 23andMe internal IDs

A 23andMe raw file has two kinds of variant identifiers. Most rows use
standard `rs####` IDs (dbSNP rsIDs). A minority — 23andMe's internal
`i####` identifiers — are custom probes 23andMe added for variants the
standard array chemistry doesn't cover well, and disproportionately
clinically important ones. Two verified examples: Prothrombin G20210A
(`rs1799963`, venous-thrombosis risk) is carried as 23andMe **`i3002432`**,
and GBA N370S (`rs76763715`, Gaucher/Parkinson association) as 23andMe
**`i4000415`**.

Every lookup in Allelio is keyed by rsID, so this version does not resolve
`i`-ID rows — they are parsed but not looked up. This is a disclosed scope
boundary, not a silent one: every `allelio analyze` and `allelio info` run on
a 23andMe file reports how many rows were skipped this way, and the same
count appears in the HTML report. If Prothrombin or GBA matter to you,
check your raw file directly for `i3002432` or `i4000415`. Resolving these
via a dbSNP coordinate mapping is planned for a future release (see
`PUBLICATION_PLAN.md`, PUB-11-full) but was deferred to avoid adding a large
reference-data dependency before this version's first release.

---

## Where the reference data lives

Allelio splits its reference data into two layers, hosted differently on purpose.

- **Clinical databases (ClinVar, GWAS Catalog, ClinGen, ClinPGx) are fetched
  live** from their sources at setup. They are curated continuously, so you want the
  freshest copy. Allelio warns you when your local copy gets old and prompts
  `allelio update`.
- **Population frequencies (gnomAD) are pinned to a permanent copy.** Allele
  frequencies barely move between releases, so Allelio ships a compact extract
  (about 24 MB, trimmed to consumer-array sites) rather than making you download
  gnomAD's raw multi-hundred-gigabyte files.

That frequency extract is stored permanently on the **permaweb (Arweave) via
[Permavault](https://permavault.co)**. The address is derived from the file's
contents, so it cannot 404 and cannot be silently swapped, and the address is
itself the integrity check. gnomAD is public-domain (CC0), so a permanent copy
carries no licensing friction. Allelio resolves the file through a small
manifest (`data/gnomad_manifest.json`), which means a future data refresh is a
one-line manifest change rather than a code change, and it keeps a GitHub
release as a mirror. On setup, Allelio downloads the extract and verifies its
SHA-256 before trusting it; a mismatch is rejected and the mirror is tried
instead. The current extract is also anchored into Bitcoin (block 965,344), so
its exact contents are provable against an independent, tamper-resistant
timestamp.

This is a deliberate resilience choice. Genomics data sources move, retire
endpoints, and occasionally disappear (the reason Allelio exists at all is the
23andMe collapse). Pinning the stable layer to content-addressed storage means
Allelio keeps working even if a provider reorganizes or goes away.

To rebuild or update the extract, see `scripts/build_gnomad_freq.py` and the
`_notes` in `data/gnomad_manifest.json`.

---

## Privacy and security

Your genome is deeply personal. Allelio was built with that in mind:

- **No cloud processing** — analysis runs entirely on your hardware, and the AI
  model has to be running on this machine too, and a remote address or an Ollama
  `-cloud` model is refused rather than warned about. The address is resolved
  and then connected to by address, so a name cannot point somewhere else
  afterwards; a proxy configured on the system is ignored rather than refused,
  and a loopback port can still be a proxy Allelio cannot see through
- **No accounts or sign-ups** — just install and use
- **No telemetry or tracking** — Allelio doesn't phone home, ever
- **No data storage** — your file is read during analysis and never saved by Allelio
- **Fully open source** — you can read every line of code to verify these claims

---

## Project structure

For developers and contributors, Allelio is organized into clean modules:

```
allelio/
├── parsers/      # File readers for 23andMe, AncestryDNA, VCF
├── database/     # ClinVar, GWAS, gnomAD, ClinGen and ClinPGx download, storage, and querying
├── analysis/     # Variant annotation and cross-referencing
├── ai/           # Local LLM integration — Ollama or any OpenAI-compatible server
│   └── safety.py # Lexical filter for unhedged diagnostic / prognostic / prescriptive language
├── web/          # FastAPI web interface (Jinja2 templates)
├── cli.py        # Command-line interface
└── report.py     # HTML report generation
```

---

## Contributing

Whether you're a bioinformatician, a developer, a designer, or just someone who wants to help — contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for how to set up a development environment, run the tests, and submit a pull request. Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).

If you use Allelio in your own work, see [CITATION.cff](CITATION.cff) for how to cite it.

---

## Troubleshooting

**"allelio: command not found"** — Python's script directory isn't in your system PATH. On Mac, try: `python3 -m allelio` as an alternative, or add the scripts directory to your PATH.

**ClinVar download fails** — The NIH server can be slow. Allelio retries automatically up to 3 times. If it still fails, wait a few minutes and run `allelio setup` again.

**"Ollama not responding"** — Make sure the Ollama app is running, or start it with `ollama serve` in a separate terminal window.

**"Model not found"** — You need to download the AI model first: `ollama pull llama3.1:8b`

**A release shows as "unknown" or "(from file date)" in `allelio info`**: "unknown" means the database was built before Allelio recorded release dates; "(from file date)" means the reference file was already on disk when the database was built, so the date is the file's own timestamp rather than the one the server reported. Either way, `allelio update` re-downloads the sources and records the real release dates and checksums.

**Analysis seems slow** — the lookups are instant; the AI explanations are what take the time, and how long they take depends entirely on your model and hardware. On an Apple Silicon Mac with `llama3.1:8b`, expect roughly half a minute per variant, so a default run (top 20) is on the order of ten minutes. `--no-ai` skips the explanations and returns findings in a few seconds, and the report is still complete, just without the plain-English write-ups.

---

## License

Allelio is released under the [MIT License](LICENSE) — free to use, modify, and share for any purpose.

---

## Disclaimer

Allelio is provided "as-is" for educational and informational purposes only. It is not a medical device and does not provide medical advice, diagnosis, or treatment recommendations. The authors and contributors are not responsible for any decisions made based on information provided by this tool. Always consult qualified healthcare professionals for medical guidance.

---

**Made with care by the Allelio community.**
