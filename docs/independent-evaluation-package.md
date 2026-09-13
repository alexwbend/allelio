# Independent evaluation package

This document defines the handoff for evaluation that must be performed by
people independent of Allelio's implementation. It does not contain reviewer
labels, ratings, adjudication or clinical-validation claims.

## Frozen materials

The software release, input cases, expected outcomes and reference snapshots must
be frozen before reviewers begin. Record SHA-256 hashes for each file and keep a
case-access log. Cases already used to develop or debug Allelio belong to the
development split and cannot become unseen validation cases. The shipped
`examples/challenges` and `examples/evaluation` bundles are templates and
development fixtures only.

An independent annotation reviewer supplies, for every held-out case:

- the supported input identity and build, or the reason it is unsupported;
- expected parsing, recovery, matching, source-selection and reporting outcomes;
- the source records and versions used to establish the expectation;
- an explicit abstention expectation where evidence is missing or ambiguous;
- their identity/pseudonym, date and conflict-of-interest declaration.

Do not pre-fill these fields with Allelio output or AI-generated labels. Freeze
the completed labels, hash them, then run Allelio without altering cases or
expectations. If a case informs a fix, disclose it as development material and
replace it in any subsequently claimed held-out set.

## Aligned local-workflow comparison

Use an established, locally runnable annotation workflow configured against the
same reference versions where its supported capability overlaps Allelio. Ensembl
VEP in offline/cache mode is the proposed comparison workflow for VCF identity
and consequence/source retrieval. It does not provide Allelio's consumer-array
parser, custom-probe recovery, report grouping or explanation features; those
stages must be marked unsupported, not scored as failures.

Create an adapter that emits the documented `allelio-benchmark/1` comparison
shape described in `regression-benchmark.md`. Pair only cases whose input and
reference fingerprints match and only stages both tools support. Preserve raw
VEP output, command/configuration, cache/plugin versions and hashes. Do not infer
alignment from rsID alone. A second annotator is a comparison arm, not clinical
ground truth; disagreements require independent adjudication.

Before execution, an independent reviewer must approve the exact shared cases,
reference alignment and expected outcomes. No VEP cache or independently curated
labels are bundled with Allelio, so this comparison is prepared but not complete.

## Blinded explanation review

Generate frozen template/model outputs using `evaluate-explanations` as described
in `explanation-evaluation.md`. Keep `private-run.json` and the blinding key from
reviewers. Give reviewers only the blinded cases, rubric, source evidence and
instructions. Two qualified reviewers should independently score factual support,
unsupported certainty, material omissions, severity, uncertainty communication
and readability, with disagreements flagged for adjudication.

Reviewers must create their own pseudonymous IDs and ratings. An untouched ratings
template is missing data, not a zero score. AI-generated ratings are not independent
review. Report missing rows/scores, disputes, fallback/abstention frequency and
the denominator for every statistic. Preserve paired/clustered case structure.

## Completion record

The evaluation can be called independent only when the package contains:

1. reviewer-authored frozen expectations and their hashes;
2. frozen Allelio and comparison-tool versions, inputs and aligned references;
3. raw outputs plus the comparison adapter and exclusions;
4. blinded human ratings, missingness and adjudication records;
5. a signed-off limitations statement and case-access log.

Until then, report the package as prepared and the independent evaluation as
pending. No outreach or data sharing is performed by the included commands.
