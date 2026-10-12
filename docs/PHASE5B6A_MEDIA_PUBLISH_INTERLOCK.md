# Phase 5B-6A — Mandatory media publish stop and legacy READY writer boundary

## Scope and limits

This phase closes the immediately dangerous **source-code** path in which a
legacy Sheets reviewer could opt out of strict review and a real Threads
publisher could infer authority from `PUBLISH_ENABLED`,
`ALLOW_REAL_THREADS_POST`, `ALLOW_MEDIA_POSTS` and the queue status.

This is a **fail-closed transition phase**, not an implementation of an
effective, publication-authorizing approval. No real IdP, protected review
database, canonical production queue store, or cross-store atomic transaction
is provisioned. No actual content is published, no production Sheets is
modified, and no common VPS commands run in this development chat.

### Boundary 1 — posting network entrypoints

`src/publishers/media_publish_interlock.py` is a pure, non-configurable
runtime policy without an environment-variable bypass. It detects physical
media parameters and published media metadata including protected media
slots (two accounts, four covered slots), media asset IDs, media URLs, clip
IDs, media type and media generation/route values. It explicitly does
**not** treat a plain reference's source-video URL as physical publication
evidence; text-only transformations continue to use their old gates.

- `src/publishers/threads_publisher.py`: non-dry-run physical media and
  media-marked queue rows are stopped before credentials, the Threads create
  container endpoint or the publish endpoint. A forged `READY`,
  `human_approved`, `authenticated_approval_integrated` or
  `publish_authorized` field never lifts the stop; even all environment
  flags true cannot bypass. Dry-run remains available.
- `src/publishers/x_publisher.py`: X's deprecated text endpoint rejects a
  media-marked row before credential reads or network calls. The X feature
  gate still applies independently. X itself remains outside the active goal.
- `scripts/process_threads_queue.py`: carries the complete canonical
  queue row to the real publisher, and evaluates the same interlock against
  the queue, derivative and originating draft before updating READY to
  PROCESSING or issuing a network call. Returns a non-writing,
  non-post-attempted safety stop for protected media.
- Media without metadata but **with actual attached media URL(s)** is
  stopped. Missing account context, mismatched account/queue ownership or
  malformed derivative context also fail closed.

### Boundary 2 — old READY writers

The old flag `strict_trusted_media_review=false` is no longer a bypass.
`scripts/media_review_legacy_guard.py` always blocks protected-media
READY promotions regardless of the CLI/Sheets reviewer configuration. It
continues to allow a text-only READY and ordinary rejection/hold/feedback.

Additional protected READY surfaces:

| Path | Enforcement |
|---|---|
| Manual `approve_queue.py` and publication review board | Mandatory strict transition block |
| `auto_approve_queue.py` evaluation | Protected media rejected even with disabled media rules |
| `auto_approve_queue.py` apply | Re-read queue, draft and derivative before changes; a missing/moved media row aborts the whole READY batch with zero writes or approval logs |
| `SheetsClient.update_queue_item` | Current row re-read; fail closed for READY/media |
| `SheetsClient.bulk_update_queue_items` | Preflight the entire batch; mixed text/media causes no batch writes |
| `SheetsClient.append_queue_item` | Blocks direct insertion of READY media |
| `MockSheetsClient` equivalents | Apply same policy during development |
| `process_threads_queue.update_row` and `append_row` | Block legacy raw worksheet READY mutation |
| Real Threads / X publish | Mandatory pre-network stop, including old media READY inventory |

All guards are **non-authorizing**; a passing text-only check is not
an authenticated media approval. No production application ID or human
reviewer field is trusted as proof of rights.

## Validation

```bash
python3 scripts/test_phase5b6a_media_runtime_interlock.py
python3 scripts/test_legacy_media_review_safety.py
python3 scripts/test_auto_approve_queue_apply_ready_only_safe_items.py
python3 scripts/test_auto_approve_queue_batches_sheets_updates.py
python3 scripts/test_auto_approve_queue_logs_reason.py
python3 scripts/test_threads_publisher_media_dryrun.py
python3 scripts/test_phase3b.py
python3 scripts/run_repository_tests.py
python3 scripts/test_all_workflows_safety_flags.py
python3 -m ruff check --select E9,F63,F7,F82 src scripts
python3 -m compileall -q src scripts
git diff --check
```

No fake signed permit is accepted by the publisher. No actual SNS credentials
or live posting API call are part of these security regression tests.

## Unresolved, not claimed done

1. **No authoritative media approval is enabled.** The 5B-5A/5B-5D
   ledger only records review. The new runtime interlock intentionally
   prohibits live media publishing regardless of status or environment.
   Successful code tests must not be interpreted as completed production
   approval integration.
2. **Google Sheets is not a database transaction.** Even when a worker
   reads the current media row, Sheets can change before a subsequent write.
   Dedicated DB authorization, content fingerprint checks and publish-time
   rights expiry/revocation evaluation remain future work.
3. **Old direct worksheet/API calls must be inventoried end to end.** These
   protections cover known central SheetsClient and Threads worker paths.
   Additional direct `gspread`, bulk tabs, historical repair jobs and
   deployments may bypass a generic Python wrapper. The publisher
   interlock still stops physical media network calls made through the two
   checked publishers; direct network requests outside those publishers
   must be audited before enabling any live media.
4. **Text-only publishing is intentionally not globally disabled.** Its
   preexisting triple-gates, quality, account and duplicate policies remain.
   Stronger cross-store identity and queue integrity for text belongs in a
   separate, risk-assessed rollout; source provenance alone is not media.
5. **Deployment and rollback are not authorized by this PR.** No jobs,
   workflows, VPS service, API token, production Sheets or live media DB
   are modified. A code merge does not establish production readiness.

## Phase 5B-6B follow-up

- Migrate reviewer + queue authority + publisher claim into a single
  transactionally coherent backend with identity, session revocation,
  proof retention and publish-time snapshot checks. Until complete,
  any media request must be refused, including those bearing signed
  mock receipts or human confirmation flags.
- Inventory all READY writers and real API endpoints (including direct
  Google Sheets grids, CLI tools, scheduled workflows and legacy code).
  Require an explicit operation ledger and test no unauthorized route.
- Build a one-use, scoped publication claim with strict account, queue,
  content digest, media digest, idempotency and external outcome handling;
  enforce rights freshness and reviewer revocation before the actual
  network call, without a race that allows duplicate publication.
- Validate on synthetic and disposable operational data, then route a
  staged production deployment, restore exercise and real canary through
  the **separate common VPS management chat** after authorization.

## Common VPS handoff (operations only)

Repository: `dev-ch-hhuk39/sns-growth-engine`. Deploy the exact merged
SHA only after full GitHub CI success and a dedicated rollout decision.
Use `/run/lock/chadult-production-deploy.lock`, run disk/RAM/resource
preflight, preserve existing snapshot/backups, verify rollback and account
isolation, ensure all media operations remain blocked before allowing any
production real-post flag. This phase has no production migration requirement.
