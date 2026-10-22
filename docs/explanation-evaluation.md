# Frozen-evidence explanation evaluation

## Internal synthetic pilot (issue #45)

The [pilot protocol](../data/evaluation/explanation-pilot-v1.protocol.json)
freezes the two existing invented `examples/evaluation` findings, current code,
prompt hashes, model manifest digests, settings, denominators and inspection
criteria before generation. These previously available fixtures are internal
development material; the bundle's historical `evaluation` label does not make
them unseen or independently curated. Neither invented record is an actual
ClinVar assertion. One has a Pathogenic label and the other Uncertain
significance. Both have one carried allele, unknown classification type,
not-curated inheritance, and no frequency, GWAS or PGx evidence.

The deterministic reference formatter runs first, once per case, with socket
connection and DNS calls denied inside the process. A second pass checks exact
text repeatability. The local comparison then uses Llama 3.1 8B and Qwen3 4B,
both Q4_K_M, with three repetitions per case through the unchanged production
prompt, local adapter, reasoning removal and safety/disclaimer formatter.
Both receive a 4,096-token output budget and 900-second request timeout. No
temperature, seed or thinking override is sent. Qwen's model metadata declares
temperature 0.6, top-k 20 and top-p 0.95; effective server settings are not
independently verified. Llama does not declare sampling defaults. The full
runtime and model metadata are retained locally.

There are **two distinct case clusters**, six call opportunities per model,
and fourteen primary output opportunities including the two templates. Repeated
template integrity passes do not add cases. The template summarizes supplied
fields; the model prompt asks for broader educational prose, so differences
have a different remit. Do not turn repetition counts into independent sample
sizes, confidence intervals, clinical accuracy or comprehension measures.

Run from a checkout matching the frozen software/runner hashes, with the exact
model digests installed in Ollama 0.40.7. Provision models separately from the
experiment. The runner does not download models or consult a reference database.
Set the following variable to a fresh local location **outside Git checkouts**:

```sh
python3 scripts/run_explanation_pilot.py --mode template \
  --output "$EXPLANATION_LOCAL_RUN/template"
python3 scripts/run_explanation_pilot.py --mode models \
  --baseline "$EXPLANATION_LOCAL_RUN/template" \
  --output "$EXPLANATION_LOCAL_RUN/models"
```

The second command verifies the completed baseline and its retained artifact
hashes. The runner checks input/prompt/software identity and model metadata
before and after generation, verifies actual request prompt hashes, and retains
each call as it finishes. Failed attempts keep an `INCOMPLETE` marker and local
diagnostics. Do not overwrite them or revise expectations to improve a result.
Retained records include stripped final answers, exact requests/options,
elapsed times, server stop reasons where supplied, error/fallback status and
output hashes. Private reasoning content is discarded; only its character
count is kept. A generated status does not imply a complete or supported answer:
inspect `done_reason`, missing content and the text itself. Model refusals in
ordinary prose require qualitative inspection; the adapter's status alone does
not classify them.

Automated checks concern provenance, selected template fields, repeatability,
lexical flags, and consistent production wrapping. They do not measure factual
quality. Any qualitative observations are attributed to Codex's internal
AI-assisted inspection against the frozen criteria. They are separate from
automated counts, human ratings and independent scientific assessment. No human
inspection is claimed by running this pilot, and rating templates stay unscored.
The two cases do not test curated inheritance, frequency, GWAS, PGx, high-impact
warnings, conflicting assertions or multi-record contexts.

Only reviewed aggregate/hash records and paraphrased observations are intended
for publication. Full synthetic answers, prompts, model metadata/licenses and
error receipts stay in the local research folder. Model weights must be acquired
upstream under their own terms: [Llama 3.1 Community License](https://ollama.com/library/llama3.1:8b/blobs/0ba8f0e314b4)
and [Qwen3 Apache-2.0 notice](https://ollama.com/library/qwen3:4b/blobs/d18a5cc71b84).
Allelio's MIT license does not relicense these resources. The protocol's
source/artifact register documents the public/local split and review date.
Hashes identify retained outputs; stochastic bitwise regeneration is not promised.
Loopback endpoint checks depend on a trusted local model server and do not
establish operating-system-level network isolation.

### Recorded pilot, 22 October 2026

The [aggregate record](../data/evaluation/explanation-pilot-v1.results.json)
records the first complete execution after protocol/runner commit
[`a138c119fdf32c4e4932ad778de885e886c7f00c`](https://github.com/alexwbend/allelio/commit/a138c119fdf32c4e4932ad778de885e886c7f00c).
Allelio 0.4.1 ran on an Apple M3 Pro, 18 GB RAM, macOS arm64, using Python
3.9.6, ollama-python 0.6.1 and Ollama 0.40.7. No case, prompt or expectation was
changed after generation. The baseline completed before any model calls.

| Automated observation | Template | Llama 3.1 8B | Qwen3 4B |
| --- | ---: | ---: | ---: |
| Primary output opportunities | 2 | 6 | 6 |
| Generated outputs | 2 | 6 | 6 |
| Fallbacks | 0 | 0 | 0 |
| Server-reported length stops | N/A | 0 | 0 |
| Lexically flagged outputs | Not assessed | 1 | 1 |
| Production safety/disclaimer wrapping verified | N/A | 6 | 6 |

Both template outputs passed the selected-field checks and matched exactly on
the second pass. The model-run template regeneration matched the original
baseline. All twelve model calls returned `done_reason=stop`, and the input,
software, prompt, baseline-artifact and model-metadata integrity checks passed.
No recognized reasoning fragments were counted as removed; this does not show
that the models did not reason internally or test every reasoning transport.
There were no ordinary-prose refusals observed during the separate inspection.
The generated count is completion/attribution accounting, not a quality score.

**Exploratory Codex inspection, separate from automated checks:** the templates
preserved the source condition/classification and uncertainty fields within
their information-only remit. Llama omitted the Pathogenic label and condition
name in all three first-case answers. In the second case, repetitions 1 and 3
retained Uncertain significance, while repetition 2 claimed no ClinVar
condition/trait association despite the supplied assertion. Some answers
expanded absent supplied evidence into claims about entire databases. The
unknown classification type was not explicitly preserved in Llama's answers.

Qwen recognized the artificial gene/condition wording, then used it to infer
harmlessness or absence of real health consequences across all six answers.
It added claims about database placeholder records, disease associations or
commonness that were unsupported by the supplied evidence. The obvious
placeholder wording influences these responses and limits the pilot's relevance
to real inputs. Recognizing an invented example is appropriate; the broader
database and personal-risk assertions do not follow from that observation.

Both models often explained heterozygosity and recommended consultation, but
used multiple sections and repeated caveats beyond the requested two-to-four
paragraphs. These are AI-assisted observations, not human readability ratings.
The two lexical warnings include genotype-related/negated fragments and do not
measure the unsupported claims described above. Notices were appended without
removing model text. The pilot cannot support a model ranking, general factual
reliability, clinical safety or comprehension claim.

Both template outputs and all twelve model outputs were inspected by Codex against the
frozen criteria. No human inspection, ratings, independent review or adjudication
is claimed. Full originals and unscored rating scaffolds remain local; the public
record retains their hashes and paraphrased observations. Internal content,
source-rights and metadata inspection covered the intended public files. No
participant records or raw model-answer payloads are included. The initial run
is preserved without prompt tuning or reruns that replace its observations.
The public package permits repeating the method. Auditing the exact generated
wording and qualitative observations requires access to the retained local
answers; hashes alone do not provide that audit. Any later public answer release
needs its own content and rights review.

## Optional independent human-review tooling

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
