# Allelio

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
2. **Looks up your variants** in two major scientific databases:
   - [ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/) — clinically significant genetic variants curated by the NIH
   - [GWAS Catalog](https://www.ebi.ac.uk/gwas/) — genome-wide association studies linking variants to traits and conditions
3. **Explains findings in plain English** using a local AI model (Ollama), so you don't need a genetics degree to understand the results
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

- **Python 3.10 or later** — [download here](https://www.python.org/downloads/) if you don't have it
- **Your raw DNA data file** from 23andMe, AncestryDNA, or in VCF format
- **Ollama** (optional but recommended) — this runs the AI that explains your results in plain English
  - [Download Ollama](https://ollama.com) and install it
  - Then open a terminal and run: `ollama pull llama3.1:8b` (downloads a ~4 GB model)
  - If you skip this, Allelio still works — you just won't get AI-written explanations

### Install Allelio

Open a terminal (Terminal on Mac, Command Prompt or PowerShell on Windows) and run:

```bash
pip install allelio
```

### Set up the databases (one time only)

This downloads the ClinVar and GWAS reference databases (~500 MB total). You only need to do this once:

```bash
allelio setup
```

### Launch the web interface

```bash
allelio serve
```

Then open your browser to **http://localhost:8080**. You'll see a clean interface where you can upload your DNA file, browse your variants, read AI explanations, and export a full report.

### Or use the command line

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

# Only show trait associations (no disease risks)
allelio analyze my_23andme_data.txt --traits-only
```

---

## Supported file formats

| Format | Source | How to get your file |
|--------|--------|---------------------|
| .txt | 23andMe | Account → Settings → 23andMe Data → Download Raw Data |
| .csv | AncestryDNA | Settings → Download DNA Data |
| .vcf | Various | Standard variant call format (v4.1+) from clinical or research sequencing |

---

## How it works under the hood

Allelio's pipeline is straightforward:

1. **Parse** — reads your genotype file and extracts your genetic variants (SNPs)
2. **Lookup** — checks each variant against the local ClinVar and GWAS databases
3. **Analyze** — gathers clinical significance, associated traits, and biological context
4. **Explain** — sends the findings to your local AI model for plain-English summaries
5. **Present** — displays results in your browser or exports them as an HTML report

The reference databases are stored locally on your machine after the initial download. During analysis, Allelio makes **zero network requests** — your data stays put.

---

## Privacy and security

Your genome is deeply personal. Allelio was built with that in mind:

- **No cloud processing** — analysis runs entirely on your hardware
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
├── database/     # ClinVar and GWAS data download, storage, and querying
├── analysis/     # Variant annotation and cross-referencing
├── ai/           # Local LLM integration via Ollama
├── web/          # Flask-based web interface
├── cli.py        # Command-line interface
└── report.py     # HTML report generation
```

---

## Contributing

Whether you're a bioinformatician, a developer, a designer, or just someone who wants to help — contributions are welcome.

**Ways to help:**
- Report bugs or suggest features via [GitHub Issues](https://github.com/alexwbend/allelio/issues)
- Submit pull requests
- Improve documentation or write tutorials
- Test on different platforms and file formats
- Spread the word

**To set up a development environment:**

```bash
git clone https://github.com/alexwbend/allelio.git
cd allelio
pip install -e ".[dev]"
```

---

## Troubleshooting

**"allelio: command not found"** — Python's script directory isn't in your system PATH. On Mac, try: `python3 -m allelio` as an alternative, or add the scripts directory to your PATH.

**ClinVar download fails** — The NIH server can be slow. Allelio retries automatically up to 3 times. If it still fails, wait a few minutes and run `allelio setup` again.

**"Ollama not responding"** — Make sure the Ollama app is running, or start it with `ollama serve` in a separate terminal window.

**"Model not found"** — You need to download the AI model first: `ollama pull llama3.1:8b`

**Analysis seems slow** — AI explanations take about 10 seconds each. The default analyzes 20 variants (~3 minutes). Use `--no-ai` for instant results without explanations.

---

## License

Allelio is released under the [MIT License](LICENSE) — free to use, modify, and share for any purpose.

---

## Disclaimer

Allelio is provided "as-is" for educational and informational purposes only. It is not a medical device and does not provide medical advice, diagnosis, or treatment recommendations. The authors and contributors are not responsible for any decisions made based on information provided by this tool. Always consult qualified healthcare professionals for medical guidance.

---

**Made with care by the Allelio community.**
