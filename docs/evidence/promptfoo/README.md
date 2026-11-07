# Genuine synthetic fixture generators

These are development evidence, not a runtime dependency or model benchmark.
Used with Promptfoo0.125.1 and Node22.23.4. No API keys or external models.

To repeat in a new temporary directory, copy the `.mjs` files and
`tests/fixtures/promptfoo/prospective-tests.json` there, then install the pinned
harness separately:

```sh
npm init -y
npm install --ignore-scripts promptfoo@0.125.1
PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1 node probe.mjs
PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1 node generate-two-runs.mjs
PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1 node probe-single-trial.mjs
PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1 node probe-repeat-one.mjs
PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1 node probe-provider-vars.mjs
```

Freeze the supplied prospective plan with the documented Python text API before
executing the harness. Do not create the plan from observed results. The Python
adapter never imports Promptfoo. Generated eval IDs/timestamps differ, so outputs
need not be byte-identical to fixtures.

The harness may warn that traces cannot be exported because database persistence
is disabled. Tests inspect actual results, not traces. The single/repeat1 probes
prove missing repeatIndex and are intentionally unsupported by this adapter.
The provider probe proves persisted vars are not execution/context attestation.
