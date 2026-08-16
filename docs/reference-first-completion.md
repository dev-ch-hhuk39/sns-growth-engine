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

The v23 report also exposes `ACTIVE_SCOPE_SOFTWARE_COMPLETE`,
`ACTIVE_SCOPE_LIVE_EVIDENCE_COMPLETE`, `DEFERRED_PLATFORM_COUNT`,
`DEFERRED_PLATFORMS` and `PRODUCTION_PUBLISH_EVIDENCE_COMPLETE`. Active
acquisition is X, YouTube and TikTok. Threads is a non-blocking
`DEFERRED_OSS_CANDIDATE`, not an authentication blocker.

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

Expected state while live production evidence remains incomplete is
`SOFTWARE_COMPLETE_EXTERNAL_BLOCKERS_ONLY`: software and no-write integration
are complete while production evidence is false. This is a successful
completion-gate result, not permission to write production systems.

## External Blockers

- X permission: the 24 explicitly authorized X/Threads/TikTok identities were
  written source/account/handle-specifically and verified read-after-write on
  2026-08-11. Third-party repost inheritance remains disabled.
- X physical Golden: four exact status URLs have recorded A/V evidence across
  Night Scout and Liver Manager. `twscrape` remains optional-auth and does not
  block the proven gallery-dl plus yt-dlp route.
- Threads reference acquisition: `DEFERRED_OSS_CANDIDATE` with reason
  `NO_APPROVED_BACKEND_ONLY_GITHUB_OSS_ROUTE_CURRENTLY_PROVEN`. Meta Graph,
  Meta oEmbed and browser routes are inactive by owner policy.
- Production mutation: Sheets, Cloudinary, download/cut and Threads publishing
  require separate explicit approval and credentials.
- Public reachability: a provider returning no posts during a bounded no-write
  probe is recorded as `UNVERIFIED_EXTERNAL`.

The applied owner decision and remaining X Golden sequence are in
`docs/x-reusable-media-permission-decision-package.json`.
