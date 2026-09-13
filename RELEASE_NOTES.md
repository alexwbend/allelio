# Allelio v0.4.0 — Traceable Evidence

This release turns Allelio's annotation output into a more explicit, reproducible
evidence workflow. It is an alpha research and educational release, not a
clinically validated diagnostic system.

## Highlights

- Versioned evidence JSON and a shipped schema, including source records,
  matching decisions, exclusions, coverage and gene groups.
- Conservative VCF identity handling with declared-build, coordinate, allele,
  ploidy and filter checks. Unsupported cases abstain instead of being guessed.
- Condition-specific inheritance and allele-specific population-frequency
  context, kept separate from source classification and display ranking.
- Deterministic gene grouping in the CLI, web interface, HTML and evidence export.
- Offline run manifests and annotation replay with software, input, reference,
  configuration and optional probe-mapping fingerprints.
- Developmental stage benchmarks and blinded explanation-review materials.
  These tools do not constitute independent clinical validation.
- Optional recovery of two documented 23andMe probes: `i3002432` to `rs1799963`
  and `i4000415` to `rs76763715`,
  when the user supplies the versioned map and the input declares the supported
  product/build context. Other internal probes remain unresolved.
- The published gnomAD v4.1.1 format-2 extract now provides allele-aware
  frequencies through verified Arweave and GitHub mirrors.

## Install and verify

Create a fresh Python 3.9–3.12 virtual environment, install the release artifact,
and run:

```sh
allelio --version
allelio setup
allelio info
allelio analyze examples/example_23andme.txt --no-ai --output example_report.html
```

The source archive contains the examples. A wheel installation contains the
runtime package but not repository examples; use your own supported input or a
separately downloaded source archive for that final command.

Reference setup downloads rolling third-party data and can take 15–30 minutes.
Optional-source failures are reported and leave the remaining sources usable;
ClinVar is required. Saved reports and evidence exports contain genetic data and
are not encrypted by Allelio.

## Reproducibility and limits

Use `record-run` and `replay-run` for a fixed local reference database. Replay
checks annotation, not stochastic model text. The synthetic challenge and
explanation bundles are development fixtures, not held-out patients or
independent assessments. No independent reviewer ratings are included in this
release.

See the README and `docs/` for supported input boundaries, reference provenance,
probe-recovery evidence, privacy checks and evaluation instructions.
