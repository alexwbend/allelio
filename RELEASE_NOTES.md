# Allelio v0.4.1

A maintenance release on top of v0.4.0 (Traceable Evidence). It adds a bounded
way to bring an existing Ensembl VEP run into Allelio's benchmark comparison,
extends support to Python 3.13 and 3.14, and corrects the citation metadata.
It is still an alpha research and educational release, not a clinically
validated diagnostic system.

## What changed

- `allelio import-vep` verifies and preserves an existing development run of
  Ensembl VEP and writes a `benchmark.json` that `allelio benchmark --compare`
  accepts. It does not run VEP or download caches, it compares only
  single-sample biallelic SNP VCFs with a declared GRCh37 or GRCh38 reference,
  and no real VEP run ships with the release. See `docs/vep-comparison.md`.
- CI and the package classifiers now cover Python 3.9 through 3.14.
- `CITATION.cff` now describes this release. The 0.4.0 entry had carried the
  wrong release date.
- Releases are now published to PyPI, so `pip install allelio` works.

The v0.4.0 evidence workflow (versioned evidence JSON, conservative VCF
identity checks, condition-specific inheritance, allele-aware gnomAD
frequencies, gene grouping, offline run manifests and replay) is unchanged.
See `CHANGELOG.md` for the full history.

## Install and verify

Create a fresh Python 3.9 to 3.14 virtual environment, install Allelio from
PyPI (`pip install allelio==0.4.1`) or from the release artifact, and run:

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
