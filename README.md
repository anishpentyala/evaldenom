# evaldenom

[![Tests](https://github.com/anishpentyala/evaldenom/actions/workflows/ci.yml/badge.svg)](https://github.com/anishpentyala/evaldenom/actions)

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

## Try the missing-case check

Python 3.9 or newer, no runtime dependencies. The repository includes an invented
four-observation fixture: two cases with two trials each. The candidate drops
both hard-case trials.

```sh
git clone https://github.com/anishpentyala/evaldenom.git
cd evaldenom
python -m pip install .
evaldenom freeze examples/cases.jsonl --metrics examples/metrics.json --output manifest.json
evaldenom audit manifest.json --run baseline=examples/baseline.jsonl --run candidate=examples/candidate-missing.jsonl
```

The audit exits 1 with `BLOCKED`, rather than approving comparison on only the
easy cases. Replace `candidate-missing.jsonl` with `candidate-complete.jsonl` for
an exit-0 `READY` report. Neither verdict establishes a score gain or verifies
that the claimed inputs and graders were actually used.

Install the pinned 0.1.0 release from [PyPI](https://pypi.org/project/evaldenom/0.1.0/):

```sh
python -m pip install evaldenom==0.1.0
```

The PyPI 0.1.0 release does not include the source-only changes described below: regular-file input admission, native audit streaming, audit memory changes, or digest-validation memory changes. Use a source checkout for those changes.

The package release is pinned separately from later repository development.
Source-install commands in this README use the checked-out code, which may be newer.

## Check a changed evaluation plan before running it

An audit checks exports against one intended manifest. Before executing a changed
plan, compare its frozen contract with the earlier one:

```sh
evaldenom manifest-diff previous-manifest.json proposed-manifest.json --output drift.json
```

Exit 0 means `MATCH`: declared cases, input digests, trials, cluster labels and
metric contracts agree. Exit 1 means `CHANGED`: the report names added/removed
cases, changed inputs or clusters, added/removed trials, and changes to metric
names, graders, directions or bounds. Exit 2 means unusable input or an output
error, with no new comparison verdict. Standard output must accept the complete report
and flush successfully before exit 0 or 1; failed help/diagnostic delivery also
exits 2. A broken destination can retain a partial JSON prefix, so a report is
usable only with its successful delivery and expected exit status. Both manifests are fully validated first;
an old output is left untouched on input errors, so check the exit status.

Case/metric list order and trial order do not matter. A missing bound differs
from an explicit bound. Numeric bounds such as `0` and `0.0` are equivalent,
matching the core audit's numeric comparisons. Nothing aligns cases by position,
selects a common subset or approves dropping a difficult case. Source-manifest
hashes identify the supplied files' JSON values, including list order, so these
hashes may differ even when the declared contracts match.

This command reads only prospective manifests, not run exports or scores. It
helps inspect denominator/rubric drift before spending on an experiment. It does
not approve the new plan or establish actual model inputs, grader implementation
or statistical comparability. Reports contain case and metric identifiers; review
them before sharing. Per-case input hashes, raw inputs and score values are not
copied into the change list. The existing `audit` command still decides export
coverage against the chosen manifest; `MATCH` is never an audit `READY` verdict.

Python callers can use `evaldenom.manifestdiff.compare_manifests(previous, current)`
with parsed manifests. File callers should use the CLI's strict JSON boundary,
which rejects repeated object members and non-JSON numeric constants.

## Audit memory (source-only, unreleased)

The audit checks every intended observation, including ones missing from both
exports. It does not build a second flat set of every intended `(case, trial)`
pair. Short trial lists are reused for membership checks; longer trial lists
get per-case sets. Missing-identity and matched-identity checks avoid temporary
full-population set differences and intersections.

The native `audit` CLI now reads each JSONL run one record at a time, opening
only the run currently being checked. It no longer retains every raw run export.
`read_jsonl(path)` still returns a list for Python callers; `freeze` and the
Promptfoo JSON adapter retain their existing materialized behavior.

Audit still holds the manifest, current run's supplied-identity counts and all
completed findings in memory. One record can itself be large, and a mostly
missing run can produce a large report. This is not a hard RAM cap or bounded
memory for arbitrary logs. All runs must finish before any report is published.
For invalid inputs, the first error encountered during sequential validation can
now be reported before a decoding error later in the same or a later run.
Verdicts and finding order for usable inputs are unchanged.

On a local synthetic whole-CLI fixture with four 8,000-record runs and four
metrics per record, three fresh-process tracemalloc peaks fell from about
92.2 MB to 7.5 MB. Median instrumented time was 3.09 s before and 2.63 s after.
The reports matched byte for byte. These are fixture-specific Python-allocation
measurements, not RSS limits or general speed promises.

## Digest validation memory (source-only, unreleased)

`input_digest` still serializes the complete value to preserve its `pyjson-v1`
format and reject cycles before validation. Its strict JSON-type validation now
walks iterator frames rather than making another list of all sibling references.
The validation stack follows nesting depth, not container width. Digests and
invalid-input diagnostics retain the previous traversal order for ordinary JSON
containers. Container subclasses are inspected through built-in storage views,
not overridden iterators: an override cannot hide a non-JSON child from strict
validation. Such pathological subclasses can now be rejected where the old walk
accepted them.

This is an allocation tradeoff, not streaming hashing or a hard memory bound.
The caller's value, serialized JSON and hash input still need memory, and an
iterator walk can cost CPU time. A local 300,000-element null-list fixture reduced
total traced peak from about 3.90 MB to 3.00 MB; wide-dictionary and nested-list
fixtures showed little total-peak change because serialization dominated. Those
are synthetic local measurements, not general speed or memory promises.

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

## Experimental native export API

A narrow [Promptfoo JSON API](docs/promptfoo-api.md) supports explicit repeat>=2,
scalar inline vars and literal equals/contains assertions for current summary-v3
JSON exports. Python API and explicit CLI, not a general config resolver or default single-trial
integration. Use its strict JSON-text boundary and read the limits first.

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

- General harness export integration is not provided. A narrow experimental
  Promptfoo JSON API and CLI are available for their documented subset only.
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
executed them. Early release. The pinned 0.1.0 package is available on PyPI; later source changes are separate. No adoption claim.

### JSON input files (source-only, unreleased)

JSON and JSONL file readers now require regular files. The opened descriptor is
checked before text is consumed. Symlinks to regular files remain supported.
On systems with `O_NONBLOCK`, writerless FIFOs are refused without waiting for a
producer. Pipes, process-substitution streams and devices are not supported
inputs. Rejection returns an input error (CLI exit 2) without a report or
replacing an existing output file.

This is an intentional input-policy tightening, not a universal read timeout:
opening or reading a regular file on a slow filesystem can still wait, and
files can change during reading. JSON decoding, duplicate-member checks and
physical JSONL line numbers for regular files are unchanged.
