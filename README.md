# evaldenom

Check that evaluation exports cover the cases you intended to measure before
comparing their scores. Offline, Python standard library only.

A paired comparison can look better because a hard case errored, disappeared,
changed its input under the same ID, used a different grader, or lost a repeated
trial. Statistical comparison tools often report their matched subset. This tool
asks a prior question: do both supplied exports satisfy the same intended contract?

It does not run models, compute significance, pick a best run, average repeated
trials, fill missing scores, retry requests, or change your dataset. A READY
report is a coverage/identity check on supplied claims, not proof that the model
saw those inputs or that an evaluator was implemented correctly.

## Install from source

```sh
git clone https://github.com/anishpentyala/evaldenom.git
cd evaldenom
python -m pip install .
```

Python 3.9 or newer. Runtime dependencies: none.

## Workflow

1. Declare intended cases before running the experiment. Each JSONL record:

```json
{"id":"case-1","input":{"question":"Example?"},"trials":[1,2],"cluster":"source-document-1"}
```

IDs and cluster labels are exact nonempty strings. Trials are explicit positive
integers, never inferred from the largest observed trial. Cluster is optional;
when declared, every export must match it exactly. It is metadata, not an
independence test. Numeric `1`, string `"1"`, and boolean `true` do not alias.

2. Declare metric contracts in a JSON array:

```json
[{"name":"accuracy","grader":"exact-match-v1","direction":"higher","min":0,"max":1}]
```

`grader` is a caller-chosen version label. Use a version/digest that actually
identifies your scoring implementation. Bounds are optional finite numbers.
Direction is `higher` or `lower`. Every intended case/trial must report every
metric; subsets, extra metrics and silent grader/direction changes block READY.

```sh
python -m evaldenom freeze examples/cases.jsonl --metrics examples/metrics.json --output manifest.json
```

The manifest keeps input digests, not raw inputs. `pyjson-v1` uses Python JSON
serialization with sorted object keys, compact separators and ASCII escaping,
then SHA-256. Array order and JSON value types matter; `1` and `1.0` differ.
Object order, whitespace and escape spelling do not. This is not RFC8785 JCS,
a cross-language canonicalization promise, anonymization, or signing. Low-entropy
inputs can be guessed by hashing candidates. Keep your raw inputs privately.

3. Export each run to this explicit format. No framework-specific parser guesses:

```json
{"id":"case-1","trial":1,"input_digest":"pyjson-v1:...64-lowercase-hex...","cluster":"source-document-1","metrics":{"accuracy":{"status":"ok","grader":"exact-match-v1","direction":"higher","value":1}}}
```

Use `input_digest(actual_input)` in your exporter, not a copied manifest digest,
to catch accidental input changes. A copied label cannot prove input identity.
`status` is `ok`, `error` or `missing`. `ok` needs a finite non-boolean real score
within any declared bounds. Error/missing remains blocking even if a stale value
is also present; the tool never treats it as success or zero. Scores are checked,
not copied into the report.

```sh
python -m evaldenom audit manifest.json --run baseline=examples/baseline.jsonl --run candidate=examples/candidate-missing.jsonl
```

Exit 0: READY, supplied exports satisfy coverage and identity contracts.
Exit 1: BLOCKED, report lists missing/duplicate/unexpected observations, metric
errors and contract mismatches. Exit 2: unusable input or output error, no new
verdict. Duplicate observations block even if identical: no last-row-wins or
implicit attempt selection. Change the intended trial plan explicitly instead.

At least two separately named runs are required, but they need not represent
independent experiments. Blank JSONL lines are ignored; findings retain physical
line numbers. Repeated JSON object members and non-JSON NaN/Infinity are input
errors, including nested objects. Unknown envelope fields are errors, not silently
ignored. IDs remain case-sensitive, with no Unicode/whitespace normalization.

`--output report.json` replaces a report only after parsing and auditing finish,
via a temporary file in that directory. A blocking audit still writes its complete
report. Input errors preserve the previous report. An output path resolving to
an input path is rejected. This is not a concurrency-safe file transaction against
hostile path replacement or a hard-link alias defense.

## Example that catches selection bias

The synthetic fixture has `easy` and `hard`, each with two intended trials.
The baseline scores the hard cases at zero. A candidate export containing only
the easy cases could show 100% on its paired-complete subset. This audit reports
both missing hard trials and refuses READY. The fixture is invented, not observed
model performance. Fixing coverage might reveal no gain; coverage alone cannot
establish a gain either way.

## Scope and existing alternatives

This is a small preflight contract, not a new statistical method or an all-purpose
evaluation platform. Related tools and the behavior their descriptions document
(checked2026-11-06):

- [evaldiff](https://toolkitlabs.org/tools/evaldiff/README.md) computes paired
  statistics, excludes unmatched rows with counts, and warns while keeping the
  last duplicate. Use it for inference after resolving your intended coverage.
- [abeval](https://github.com/mohammadi-hadi/abeval) offers paired comparisons,
  intervals, power and judge-noise analysis; unmatched items are dropped/reported.
- [MLflow](https://mlflow.org/docs/latest/genai/eval-monitor/comparing-evaluation-runs/)
  pairs rows, reports unmatched/duplicate rows and skips scorer-error pairs.
- [errorbars](https://github.com/antonsoo/errorbars) already validates identity,
  cluster assignments and repeated observations, and provides statistical
  inference. It is a stronger alternative when its data model fits your workflow.
- [eval-run-manifest](https://pypi.org/project/eval-run-manifest/) records run
  provenance and directory digests. This tool instead checks intended
  case/trial/metric closure across supplied exports; neither is execution attestation.
- [EVALSIG](https://github.com/vtensor/evalsig/blob/main/docs/concepts/paired-vs-unpaired.md)
  explains paired versus unpaired inference. This tool does not choose either test.

No claim that these tools hide their exclusions, that this project is unique,
or that a blocked strict contract invalidates every possible subset analysis.
A justified subset analysis needs an explicit separate plan, not a silent change
in denominator.

## Limits

- You must write an exporter to this format. No native harness integration yet.
- A manifest created after seeing results can encode selective inclusion.
- Input digests, grader versions and cluster labels are supplied claims, not
  authenticated execution evidence. No code/model/dataset attestation.
- READY does not check uncertainty, statistical dependence, rubric validity,
  sample representativeness, model provenance, leakage or multiple comparisons.
- Every case has the same declared metric set; sparse metric plans are not supported.
- Data is retained in memory, including the intended identity set and findings.
  This is not bounded-memory processing for arbitrarily large logs.
- Finite numbers within Python float range are accepted as scores/bounds.
  No numeric string, bool or extreme integer coercion. No score arithmetic occurs.
- Reports include case/metric identifiers and run labels; review before sharing.
  Input files and manifests can contain private metadata.

## Development

```sh
pip install -e . pytest
python -m pytest -q
```

Authorship: implementation, documentation and synthetic tests were produced by
an AI assistant working on Anish's behalf. Anish has not personally reviewed or
executed them. Early source release, not a published PyPI package. No adoption claim.
