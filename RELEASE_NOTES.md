# Allelio v0.1.0 — Initial Release

**Privacy-first local genomics analysis powered by AI**

We're excited to share the first public release of Allelio — a free, open-source tool that helps you understand your DNA data without uploading anything to the cloud.

---

## What's in this release

### Analyze your DNA locally
Upload your raw genotype data from 23andMe, AncestryDNA, or in VCF format. Allelio cross-references your genetic variants against two trusted scientific databases (ClinVar and GWAS Catalog) and explains the findings in plain English — all on your own computer.

### AI-powered explanations
Using Ollama (a local AI model), Allelio generates clear summaries of complex genetic findings. No data is sent to any external server.

### Two ways to use it
- **Web interface** — a clean browser-based UI with drag-and-drop upload, interactive variant browsing, and one-click report export
- **Command line** — powerful CLI for scripting and batch analysis

### Key features
- Multi-format support: 23andMe (.txt), AncestryDNA (.csv), VCF (v4.1+)
- ClinVar and GWAS Catalog cross-referencing
- Beautiful HTML report generation
- Configurable analysis depth (number of variants, trait-only mode, etc.)
- Medical disclaimers and responsible AI guardrails throughout
- One-command setup: `allelio setup` downloads ~500 MB of reference data

### Privacy by design
- Zero network requests during analysis
- No telemetry, tracking, or analytics
- No accounts required
- Your genetic data is never stored or transmitted

---

## Getting started

```bash
pip install allelio
allelio setup          # one-time database download (~500 MB)
allelio serve          # launch web UI at http://localhost:8000
```

For AI explanations, install [Ollama](https://ollama.com) and run `ollama pull llama3.1:8b`.

See the [README](README.md) for full documentation.

---

## What's next

See our [ROADMAP](ROADMAP.md) for planned improvements including gnomAD population frequency integration, gene-level variant grouping, polygenic risk score estimates, and PharmGKB pharmacogenomics support.

---

## Important disclaimer

Allelio is for educational and informational purposes only. It is not a medical device and does not provide medical advice. Always consult qualified healthcare professionals before making health decisions based on genetic information.
