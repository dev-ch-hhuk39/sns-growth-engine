# Reference-first Completion Contract

The current owner scope is `night_scout` and `liver_manager`. Discovery remains
TikTok, Threads, X, YouTube; current physical media is X and YouTube. New
Threads/TikTok physical media is deferred. Historical account capabilities and
acceptance criteria remain retained; they do not grant current owner rights.

`scripts/evaluate_reference_first_completion.py` separates software/integration
contracts from real production evidence. A successful software-only exit with
`SOFTWARE_COMPLETE_EXTERNAL_BLOCKERS_ONLY` does not mean the whole product is
complete and does not authorize a production operation.

- `SOFTWARE_COMPLETE` requires the existing architecture, regression,
  discovery, publisher, permission/provenance and metrics/PDCA code contracts.
- `INTEGRATION_COMPLETE` covers both accounts' synthetic no-write source,
  parent/media, understanding, routing, generation, validation and review flow.
- `ACTIVE_SCOPE_LIVE_EVIDENCE_COMPLETE` additionally requires current local
  X/YouTube artifacts for both accounts, full bound visual proof, every existing
  quality gate and two uncached reads of the live permission ledger.
- `PRODUCTION_EVIDENCE_COMPLETE` additionally requires all production
  capability evidence, a valid unchanged implementation revision and its
  explicit approval, successful permission state, software and integration.
  It does not execute publication. Actual publishing has separate authority.

## Default offline evaluation

After the repository harness:

```bash
python3 scripts/evaluate_reference_first_completion.py \
  --repository-tests-json /absolute/repository-tests.json \
  --output /absolute/reference-first-completion.json
```

The default does not connect to Sheets or open physical artifact directories.
The current physical check is `NOT_RUN`, and live/production completion stays
false. Historical `PASS_AV` declarations remain visible as historical data;
they cannot substitute for actual files or make current verification pass.
Existing regression minimums, capability criteria and production approval
requirements are retained. When physical verification is explicitly requested,
a blocked result makes the command fail even if software-only checks pass.

## Explicit existing-artifact verification

Only after approval to read the existing protected Sheets configuration and
current permission ledger, on the trusted environment containing the artifacts:

```bash
python3 scripts/evaluate_reference_first_completion.py \
  --repository-tests-json /absolute/repository-tests.json \
  --verify-existing-owner-goldens \
  --x-dir /absolute/existing-x-artifacts \
  --youtube-dir /absolute/existing-youtube-artifacts \
  --output /absolute/reference-first-completion.json
```

Both existing absolute directories must be owned by the executing user with
mode 0700 and no linked path components. Media, metadata and proof files must
be owned regular single-link files without group/world write permission.
Their identities and mutable metadata are rechecked after verification.
The exact registered manifest must cover both accounts on both physical
platforms. Missing, duplicate, foreign, deferred or misbound candidates fail
before any ledger read. All selected manifest artifacts remain required; no
candidate is silently dropped to obtain a passing result.

Existing file SHA256, extracted author/native-post identity, complete Gemini
proof, A/V, geometry, persona/public-text and generation/media-text quality
checks remain mandatory. The actual media provider is not called. After local
verification, a second uncached live-ledger read invalidates prior success if
permission was revoked or account/author scope no longer matches. Mock/dry-run
clients, failed reads and missing proof block success. Output contains fixed
status/identity fields, never unpublished generated captions or raw provider
errors. No schema setup, Sheets mutation, download, cut, upload, paid inference,
READY promotion or SNS publication is performed.

Current owner verification covers X/YouTube only. Historical TikTok physical
records are not required or opened, and no Threads/TikTok physical route is
reactivated. Those platforms' non-browser metadata discovery remains separate.

## Implementation-bound approval

A normal checkout requires its own Git root, a valid 40-hex HEAD and successful
clean status. An immutable deployed release uses its exact owner-controlled,
regular, single-link, non-writable-by-others `.production-release` marker,
matching its release directory. Linked, replaced, malformed or missing markers
cannot fall back to an ancestor checkout. Empty identities never approve empty
approval values. The implementation revision must remain unchanged through the
evaluation; a change invalidates production completion.

A valid bound approval does not replace current files, latest rights, actual
capability evidence, human review, accepted reserves, schedule integration,
explicitly approved publishing canaries or timed observation. Synthetic tests
are not live evidence. Formal goal status is updated only by the established
collector/evaluator process, never manually to reflect these tests.

## Source validation — 2026-10-31

Final implementation 72efd03 passes 35 new adversarial/CLI/identity tests,
22 existing artifact integration tests, Golden25 and owner-policy21, plus
repository 1,109/1,109, isolated pytest 173/173 and workflow safety 619/619.
Compile, fatal Ruff, diff and working/history secret checks pass. Existing eight
external and three optional exclusions remain unchanged. The validation follow-up
changes documentation only. No live physical verification or production
operation was executed, and formal goal status remains unchanged.
