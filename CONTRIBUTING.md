# Contributing to Allelio

Thanks for considering a contribution. Allelio is maintained by one person as
an independent, open-source project, so contributions of any size are
genuinely useful — a typo fix, a bug report, or a new feature are all welcome.

By participating, you're expected to follow the [Code of
Conduct](CODE_OF_CONDUCT.md).

## Ways to help

- Report bugs or suggest features via [GitHub
  Issues](https://github.com/alexwbend/allelio/issues)
- Submit pull requests for fixes or features
- Improve documentation or write tutorials
- Test on different platforms and genotype file formats
- Spread the word

## Setting up a development environment

```bash
git clone https://github.com/alexwbend/allelio.git
cd allelio
pip install -e ".[dev]"
```

This installs Allelio in editable mode plus the test dependencies (`pytest`,
`pytest-asyncio`).

## Running the tests

```bash
python3 -m pytest -q
```

The full suite runs offline — no network calls, no live Ollama daemon, no
downloaded databases required. External services (ClinVar/GWAS/gnomAD
downloads, the local LLM) are stubbed or faked in tests; a live database or
model server is never needed to run them. Tests live in `tests/`, one file
per module roughly (`test_parsers.py`, `test_analysis.py`, `test_ai_engine.py`,
and so on), with shared fixtures in `tests/conftest.py`. If you add behavior,
add a test for it in the same style — small, offline, and named for what it
verifies rather than which function it calls.

CI (`.github/workflows/tests.yml`) runs the same command across Python
3.9–3.12 on every push and pull request; a PR should pass it before merging.

## Code style

There's no enforced formatter or linter yet, so match the surrounding code:

- Type hints on function signatures, especially public ones.
- Docstrings on public functions and classes (Args/Returns style), but avoid
  restating what a well-named function already makes obvious — comments and
  docstrings are for the parts that would otherwise surprise a reader (a
  non-obvious constraint, a workaround, why a value is what it is).
- Prefer small, focused functions over one that does several things.
- If you're adding a constant that drives clinical or scientific behavior
  (a threshold, a weight, a cutoff), cite the source if there is one, or say
  explicitly that it's an author choice — see `allelio/analysis/lookup.py`
  for the pattern.

## Submitting a pull request

1. Fork the repo and create a branch off `main`.
2. Make your change, with tests.
3. Make sure `python3 -m pytest -q` passes locally.
4. Open a pull request describing what changed and why. Reference any
   related issue.
5. Keep the PR focused — a fix or one feature per PR is easier to review
   than a bundle of unrelated changes.

## Reporting bugs

Open a [GitHub Issue](https://github.com/alexwbend/allelio/issues) with:

- What you expected to happen, and what happened instead
- Your OS, Python version, and how you installed Allelio
- Steps to reproduce, and any relevant error output

Please don't attach real genomic data to a bug report — a synthetic
excerpt or the example file under `examples/` is safer for you and easier
to share.
