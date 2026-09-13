# Local run manifests and offline replay

`allelio record-run` records the input fingerprint, exact installed package
contents, reference contents and source versions, runtime versions and annotation
settings. Its local manifest contains no genotype rows, absolute paths, endpoint
URLs, credentials, environment dump, or model exception text. An input checksum
can still identify a sensitive file: keep the manifest local unless deliberately
sharing it. Evidence and explanation text are written only when explicitly requested.

## Synthetic demonstration

With Allelio installed, run from the repository directory:

```sh
python3 examples/replay/build_references.py /tmp/allelio-synthetic.db
allelio record-run examples/replay/synthetic.txt \
  --database /tmp/allelio-synthetic.db --manifest /tmp/allelio-run.json \
  --evidence-output /tmp/allelio-evidence.json
allelio replay-run /tmp/allelio-run.json --input examples/replay/synthetic.txt \
  --database /tmp/allelio-synthetic.db
```

These deliberately invented rows are developmental software fixtures distributed
under the repository's MIT license. They are not patient data, external reference
material, or evidence of clinical validity. The installed-wheel integration test
performs the same record/replay operation with network connection and resolution
attempts denied, outside the repository import path.

## What is checked

Replay requires explicit input and database paths; the manifest contains neither.
It opens an existing database read-only, in a consistent SQLite read transaction.
It never initializes, migrates, downloads, or replaces references. The fingerprint
covers table definitions and deterministically ordered typed rows, including
committed data still in the SQLite WAL. A checkpoint or different database file
layout does not change it. Source release labels and source-file checksums are
also recorded; unavailable metadata remains null. The logical database hash
verifies installed content, not the existence of the original downloaded files.
Hashing a full database can take minutes and holds a read snapshot during annotation.

The package fingerprint covers Allelio's Python, JSON and HTML resources and
works without Git, including a wheel install. Replaying requires the same bytes
and version, not merely a matching version label. Runtime differences are
reported; replay still has to match the output exactly. Dependency versions,
Python implementation/version and SQLite version are recorded without a full
machine or environment inventory.

Input, package or reference mismatches fail before annotation. Output mismatches
fail after annotation. Both ends check the input checksum to detect ordinary
concurrent edits. Keep input files unchanged while recording/replaying. This is
an integrity/reproduction tool, not a signature or protection against a malicious
party modifying both the manifest and its inputs.

`--verify-only` checks prerequisites without rerunning annotation. It does not
claim an annotation match. A normal replay compares canonical evidence with only
its wall-clock `generated_at` field excluded. It includes inputs, findings,
coverage, trace decisions, provenance and settings. `--evidence-output` saves the
replayed evidence explicitly. All output paths must differ from inputs, references,
SQLite sidecars and each other, including hard-link and symlink aliases.

The `allelio-run/1` schema ships as `allelio/schemas/run-1.json`. Unknown options
or malformed manifests are rejected. Supported annotation flags are
`--include-benign`, `--include-reference`, `--no-frequency-adjustment`,
`--traits-only` and `--detailed-trace`. The fixed PGx threshold is recorded too.

## Optional explanations

Add `--explanations-output /tmp/explanations.json`, optionally with `--model` and
`--top`, to request the existing local AI adapter. Annotation-only runs never
construct or contact it. Existing loopback endpoint checks and no-redirect rules
apply. The manifest records the configured and selected model, backend, available
Ollama listing digest, prompt-template hash, output cap, timeout, one-run setting,
connection status and fallback counts. Unspecified server temperature/seed and
unavailable digests remain null; model names are not treated as immutable digests.
No extra model query is made to invent missing metadata. A failed connection can
produce the existing labelled template fallback, which is counted explicitly.

Replay always verifies annotation only. It works when the original model is
unavailable and does not certify model identity, availability or stochastic AI
output reproducibility. Explanations remain separate local artifacts. Independent
explanation evaluation is separate work.
