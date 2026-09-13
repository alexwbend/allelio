# Frozen-evidence explanation evaluation tooling

This builds local evaluation materials. It does not recruit raters, perform an
independent evaluation or establish clinical validity.

```sh
allelio evaluate-explanations examples/evaluation/bundle.json --output /tmp/allelio-eval
# Optional local model arms, only when explicitly requested:
allelio evaluate-explanations examples/evaluation/bundle.json \
  --model local-model-a --model local-model-b --repetitions 3 \
  --output /tmp/allelio-eval-models
allelio summarize-ratings /tmp/allelio-eval/blinded-cases.json \
  /tmp/allelio-eval/ratings-template.json --output /tmp/allelio-eval/summary.json
```

The last command on an untouched template reports missing scores; it is not an
assessment. Replace pseudonymous rater IDs and fill ratings before interpreting
any summaries. Do not overwrite prior experiment directories.

## Frozen inputs and comparison arms

The separate `examples/evaluation` split contains invented MIT-licensed cases;
these are not the safety/prompt-tuning fixtures. A versioned evaluation bundle
references frozen evidence, the originating run manifest and a finding ID.
Evidence must pass its schema and match the run's annotation checksum. Current
reference databases are never consulted or silently substituted. Frozen cases
should change only as reviewed dataset revisions, not in response to prompt tuning.
External material additionally requires provenance, documented reuse rights and
a local rights document before generation; those declarations need human review.

The baseline is the existing deterministic reference-template formatter, with a
neutral heading. Each explicitly configured local model sees the same hydrated
frozen finding through the existing prompt builder and safety gate. It uses the
existing local adapters and their endpoint restrictions. All prompts are identical
for repeated calls of the same case. Baseline output is generated once; each model
arm has 1–10 repetitions. Unspecified seed/temperature remain unknown server
settings, so stochastic reproducibility is not promised.

`private-run.json` retains model/backend, available digest, prompt and evidence
hashes, origin run hash, package/runtime identity, generation settings, repetition
counts, output status and the blinding key. Model refusals/fallbacks remain failed
arm outputs; their template fallback is not passed off as model-generated text.
They are excluded from blinded rating opportunities and counted separately. Keep
this file private from raters until ratings are locked.

`blinded-cases.json` has opaque random IDs, shuffled order, evidence and text,
without arm/model/repetition metadata. Style or self-identification in generated
text may still reveal an arm: this is identity masking, not guaranteed blinding.
Share only the appropriate blinded materials with reviewers, deliberately and with
reuse authorization. Nothing is sent to reviewers by these commands.

## Ratings and denominators

The exported `ratings-schema.json` describes factual support, unsupported certainty,
material omissions, severity, uncertainty communication and readability. Ratings
are integers 0–3 with explicit direction/anchors; null is unrated. Scores have
opposite directions across dimensions and are never pooled into an overall score.
Each row identifies a blinded case and pseudonymous rater, all six scores, a
dispute flag and an optional comment. `ratings-template.json` starts unscored.

The importer checks schema, the blinded-export checksum, known case/rater IDs
and unique case-rater pairs. It retains every submitted row, missing score and
dispute. Denominators are declared raters × blinded cases, with missing rows,
missing scores, disputes and scored observations shown separately. Disputed rows
are excluded from score distributions and pairwise agreement, but remain in the
output for adjudication. Agreement is raw exact agreement over available,
non-disputed rater pairs per case/dimension, not a chance-corrected statistic or
expert judgment. No comparison is reported as zero when its denominator is absent.
Synthetic-rating tests exercise this accounting; no substantive expert review has
been completed by running the software tests.
