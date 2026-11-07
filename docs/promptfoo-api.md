# Experimental Promptfoo JSON API

This is a narrow adapter for a tested subset of Promptfoo 0.125.1
exports, with Python APIs and explicit CLI commands. It is not a general config resolver. Use explicit
per-test repeat of at least 2, scalar inline vars, literal `equals`/`contains`
assertions, and the current JSON wrapper with nested summary version 3.

Default single trials and explicit repeat 1 are unsupported: genuine exports from
both omit `repeatIndex`. Missing identity is rejected, never guessed as trial 1.

## Freeze before running Promptfoo

Write the exact inline tests you intend to execute to `planned-tests.json`:

```json
[
  {
    "vars": {"question": "easy"},
    "metadata": {"external_case_id": "easy"},
    "options": {"repeat": 2},
    "assert": [{"type": "equals", "value": "OK"}]
  }
]
```

Freeze the intended contract before seeing either run's results:

```python
import json
from pathlib import Path
from evaldenom.promptfoo import manifest_from_inline_tests_text

manifest = manifest_from_inline_tests_text(
    Path("planned-tests.json").read_text(encoding="utf-8"),
    grader="my-literal-rubric-v1",
)
Path("planned-manifest.json").write_text(
    json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
)
```

Then execute those exact tests in Promptfoo, without defaultTest inheritance,
scenarios, generators, transforms, variable expansion or extra test options.
The helper checks only the supplied test list, not a surrounding config. It cannot
prove that the same list was executed. A manifest made after results can encode
selective inclusion.

Use stable, unique `metadata.external_case_id` values. The adapter uses this ID
and zero-based exported `repeatIndex`, not positional `testIdx`. Freeze rejects
unsupported test fields and more than 100,000 total intended observations. It does
not truncate to fit that budget. `cluster` is not part of this adapter's plan.

## Command-line workflow

The CLI uses the same strict JSON parser and narrow adapter contract as the APIs.
No Promptfoo installation or provider access is required for this offline audit.
Freeze before producing either export:

```sh
evaldenom promptfoo-freeze planned-tests.json \
  --grader my-literal-rubric-v1 --output planned-manifest.json
```

Write `selections.json` with one exact entry per run label. Provider IDs must be
those in each actual export, not the example IDs below:

```json
{
  "baseline": {
    "provider_id": "my-baseline-provider",
    "prompt_index": 0,
    "grader": "my-literal-rubric-v1"
  },
  "candidate": {
    "provider_id": "my-candidate-provider",
    "prompt_index": 0,
    "grader": "my-literal-rubric-v1"
  }
}
```

```sh
evaldenom promptfoo-audit planned-manifest.json \
  --run baseline=baseline-export.json --run candidate=candidate-export.json \
  --selections selections.json --output report.json
```

Exit codes match the core audit: 0 means READY for the supplied claims, 1 means
BLOCKED, and 2 means an unusable input or I/O error with no new verdict. Omit
`--output` on audit to print the report to stdout. Inputs cannot be used as output
paths, including symlink aliases. Existing output is replaced atomically only
after a complete audit. An error leaves an old report untouched, so always check
the command's exit status rather than treating an existing report as fresh.

The input file formats are deliberate: prospective tests are a JSON array,
exports are complete JSON wrappers (not JSONL), and selections are a JSON object.
Repeated members, non-JSON constants, missing labels and implicit selections are
rejected. Run labels must be unique `NAME=FILE` entries; filenames may contain `=`.
This does not add support for default single trials or any other unsupported
Promptfoo features described above.

## Audit actual JSON exports

Produce each JSON export with Promptfoo's documented output mechanism. The
current SDK writes `outputPath` from the test-suite object, not its runtime
options. This documentation mismatch is already tracked by upstream PR #9059.
No Promptfoo dependency is needed to read the resulting JSON here.

```python
from pathlib import Path
from evaldenom.promptfoo import audit_promptfoo_export_texts

report = audit_promptfoo_export_texts(
    Path("planned-manifest.json").read_text(encoding="utf-8"),
    {
        "baseline": Path("baseline-export.json").read_text(encoding="utf-8"),
        "candidate": Path("candidate-export.json").read_text(encoding="utf-8"),
    },
    {
        "baseline": {
            "provider_id": "my-baseline-provider",
            "prompt_index": 0,
            "grader": "my-literal-rubric-v1",
        },
        "candidate": {
            "provider_id": "my-candidate-provider",
            "prompt_index": 0,
            "grader": "my-literal-rubric-v1",
        },
    },
)
print(report["status"])
print(report["source_adapters"])
```

Always select each provider/prompt slice explicitly. Reports show source,
selected and excluded record counts. READY refers only to that selected slice,
not all providers/prompts in the export. Names are exact, with no fuzzy matching.
Unknown/missing selection and missing stable identity raise `InputError`.

Use these text APIs for files. They apply the core strict JSON parser, rejecting
repeated members and NaN/Infinity. The low-level object APIs cannot recover
members that a caller's last-wins `json.load` already discarded.

Assertion failure remains a valid graded zero when aggregate grading evidence
agrees with the row. Its aggregate grading score must be a finite JSON number:
booleans do not count as numeric 0/1. Equivalent finite integer/float scores are
accepted. Provider/execution error stays blocking, even with stale
score 0. Duplicate trials block; no last-row-wins or implicit attempt selection.
Coverage is checked against the prospective plan, not the intersection of the
observed exports. Two runs missing the same hard case still block.

## What READY does not prove

Input identity binds exported vars plus literal assertion definitions. It does
not bind changing candidate prompts or provider/model configuration. Grader
versions are caller labels, not evaluator attestation. This checks only aggregate
scores, not separate per-assertion metric contracts. The pinned JSON schema is
not a promise about every Promptfoo version or exporter.

A real local-provider probe saw runtime `__eval*` fields and modified call-context
vars, but the harness persisted neither in result.vars. The audit therefore
returns READY for unchanged exported claims. It cannot establish what a provider
actually executed. Richer providers and transforms are not verified here.

No model calls, retries, averaging, imputation, statistical test, dataset edit,
package publication or adoption claim. The Python adapter is offline and adds
no runtime dependency. Source JSON can include private prompts, results and
config: keep it private and review report identifiers/selections before sharing.

## Reproduce the evidence

Run `python -m pytest -q`. Tests use genuine synthetic local-provider exports
from pinned Promptfoo 0.125.1, not real model performance. Complete six-row runs
pass; shared omissions, duplicates, assertion drift, errors, invalid scores,
raw duplicate members and unsupported trial identity fail closed.

Sources checked 2026-11-06:

- https://www.promptfoo.dev/docs/configuration/outputs/
- https://www.promptfoo.dev/docs/configuration/test-cases/
- https://www.promptfoo.dev/docs/usage/node-package/
- https://github.com/promptfoo/promptfoo/pull/9059

Related interchange tools exist. This is a small intended-denominator check,
not a claim that current evaluation tools lack validation or that this adapter
is unique. AI-authored/tested on Anish's behalf; no claim of his personal review.
