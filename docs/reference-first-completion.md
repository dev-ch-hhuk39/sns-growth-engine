# Reference-first Completion Contract

Updated: 2026-08-11

`scripts/evaluate_reference_first_completion.py` is the mechanical completion
gate. It separates three claims that must never be collapsed into one:

- `SOFTWARE_COMPLETE`: architecture, regression suite, acquisition plans,
  dual-account integration contracts, publisher, permission/provenance,
  metrics and PDCA code are green.
- `INTEGRATION_COMPLETE`: both managed accounts traverse source identity,
  parent/media attachment, understanding, route selection, persona generation,
  public validation, review eligibility, geometry and permission checks with no
  external calls or production writes.
- `PRODUCTION_EVIDENCE_COMPLETE`: live capability evidence, current
  implementation-bound production approval and required source permissions
  exist. Code alone can never make this true.

Run after the repository harness:

```bash
python3 scripts/evaluate_reference_first_completion.py \
  --repository-tests-json /tmp/reference-first-repository-tests.json \
  --output /tmp/reference-first-completion.json
```

The evaluator checks executable publisher markers for text/image/video/
carousel support, READY-only selection, final validation, idempotency,
read-after-write and metric scheduling. It also checks 24h/72h/7d scheduling,
the six metrics collection outcomes, MEASURED-only PDCA, and non-auto-applied
review suggestions.

The evaluator is repository-contained. Recorded physical Golden evidence is
declared in `config/reference_first_completion.json`; it never depends on the
local-only `.codex-owner-context` directory at runtime.

Expected state before owner decisions is
`SOFTWARE_COMPLETE_EXTERNAL_BLOCKERS_ONLY`: software and no-write integration
are complete while production evidence is false. This is a successful
completion-gate result, not permission to write production systems.

## External Blockers

- X physical media: code ready, but current valid reusable-media permission
  rows are zero. Owner selection and source-specific evidence are required.
- Production mutation: Sheets, Cloudinary, download/cut and Threads publishing
  require separate explicit approval and credentials.
- Public reachability: a provider returning no posts during a bounded no-write
  probe is recorded as `UNVERIFIED_EXTERNAL`.

The exact owner input and X Golden sequence are in
`docs/x-reusable-media-permission-decision-package.json`.
