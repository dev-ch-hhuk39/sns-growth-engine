# Phase 5B-6Q — Action-free bounded Threads metrics aftercare (code only)

Status: **local implementation/test; NOT activated or deployed**.
Date: 2026-10-13 JST.

## Purpose and what was actually implemented

The production publisher already has a VPS cron/manual entrypoint in
`scripts/run_buffered_production_host.sh`. The post-publication 24/72/168-hour
metrics worker `scripts/process_threads_metric_jobs.py`, however, was
principally driven by `.github/workflows/production-autopilot-aftercare.yml`.
The latest owner policy is **not to use GitHub Actions CI or automation**, and
any shared-VPS execution must be handled by the separate common-VPS Ops team.

This phase adds
`scripts/run_buffered_metrics_aftercare_host.sh`: an independent, code-only
entrypoint to invoke the existing metrics worker without GitHub Actions.
It adds **no cron**, changes **no deployed service**, and runs **no Google
Sheets, Threads Insights API, paid AI, video, media, SNS publish, SSH or VPS
operation** as part of development. It does not create a competing database,
queue, collector or content-generation flow.

The existing worker itself now validates three write-scope properties
**before loading a write-capable SheetsClient**: an explicit
`--confirm-metrics` for `--apply`, mutually exclusive
`--dry-run`/`--apply`, and one named account rather than
`--account-id all` for apply. An all-account read-only plan remains valid.

## CLI contracts: three strictly separate modes

All commands below describe the **source code's interface**, not verified
deployment on the production host.

1. `--plan` (default) is **fully offline**: validates an explicit
   `night_scout` or `liver_manager` account, prints a plan-only JSON,
   and exits before reading the current-release symlink, any credential file,
   lock, Sheet, SNS token or network. Beauty and `all` are rejected.
2. `--dry-run --confirm-readonly` requires a real, approved
   VPS runtime/credential configuration and acquires the existing common
   deployment lock plus Sheets/account locks. It runs the **existing worker**
   with `--dry-run --use-sheets`. It can READ Sheets but cannot write
   or call SNS Insights to collect metrics.
3. `--apply --confirm-metrics` additionally requires protected
   `AFTERCARE_METRICS_WRITE_APPROVED=true` **and**
   `AFTERCARE_ACTIONS_DISABLED_ATTESTED=true` from the owner-managed
   mode-0600 `runtime.env`. It first runs the read-only preflight and then
   executes **one bounded** worker invocation with `--apply`.
   Neither mode posts to Threads/X, creates media, calls Gemini, or runs
   attribution/READY generation.

Live processing is limited to the existing at-most-20-due-jobs worker,
with bounded execution time and the existing snapshot-resume,
account-isolation, read-after-write and no-blind-retry contracts.
An ambiguous or failed worker outcome terminates the invocation; this
wrapper never auto-retries a specific write.

An active operator's process environment alone **cannot** enable writes:
both approval flags are `unset` before sourcing the protected
`runtime.env`.

## Offline smoke / quality verification

```bash
bash scripts/run_buffered_metrics_aftercare_host.sh --account-id night_scout --plan
bash scripts/run_buffered_metrics_aftercare_host.sh --account-id liver_manager --plan
python3 scripts/test_buffered_metrics_aftercare_host.py
python3 scripts/test_metrics_aftercare_apply_preflight.py
python3 scripts/test_metrics_reservation_recovery.py
python3 scripts/test_process_threads_metric_jobs.py
python3 scripts/run_local_quality_gate.py --mode full
```

The dry-run/apply modes are **NOT safe to execute as an ordinary
developer smoke check**, because they read live credentials/Sheets and
apply could write. All tests here invoke the offline `--plan` branch or
validate early-fail behavior with a non-existent fake runtime; they do not
touch production.

## Phase 5B-6R/6S bundled: same-run PDCA + inventory previews

The original 6Q metrics host is extended in place; there is **no new
daemon, scheduler, cloud deployment path or database**.

- `--with-feedback-preview` is optional. In an offline `--plan`, it
  only adds two stage names to the JSON, without opening credentials.
  In an authorized read-only `--dry-run` (or **after** one approved
  metrics `--apply`), it then invokes the *existing* measured-attribution
  runner and text-READY inventory runner with
  `--account-id <exact account> --dry-run --use-sheets`.
- The shared Sheets lock and exact account lock are now held on file
  descriptors across **all stages** of one invocation, including
  the first metrics plan and any approved write. No release or
  account-switch race can occur between these phases. The immutable
  release remains pinned under the common deployment lock.
- Attribution preview makes **no** `post_attributions` or
  `strategy_state` writes; READY preview makes **no** AI/Gemini
  requests, candidate generation, queue promotion or posting, and
  never changes another account. Both are bounded and sequential.
- `run_growth_attribution_cycle.py` now denies unconfirmed,
  ambiguous-source, broad-account and contradictory apply requests
  **before opening Google credentials/Sheets**.
- `maintain_text_ready_inventory.py` now rejects broad-account
  apply and invalid horizon before provider I/O. Read-only
  `--dry-run --use-sheets` constructs a `SheetsClient(dry_run=True)`
  instead of a write-capable one.
- **Partial completion is not atomic:** if the approved metrics worker
  writes results and then an attribution or inventory preview fails,
  previously written metrics remain valid; the host fails without
  auto-retrying any Sheets or Threads API call. This needs an
  independent operations review, not a blanket retry.

Examples that are safe on a developer Mac (offline only):

```bash
bash scripts/run_buffered_metrics_aftercare_host.sh   --account-id night_scout --plan --with-feedback-preview
python3 scripts/test_action_free_feedback_cli_gates.py
python3 scripts/test_buffered_metrics_aftercare_host.py
```

Once separately approved and installed by VPS Ops, the intended
**read-only** account inspection syntax is:

```bash
/opt/github-runners/sns-growth-engine/.buffered-runtime/current/scripts/run_buffered_metrics_aftercare_host.sh   --account-id night_scout --dry-run --confirm-readonly   --with-feedback-preview --trigger manual
```

This is **not** permission to invoke that command from a development
session; unlike `--plan`, `--dry-run` accesses the real workbook.

The next remaining **write** integration is a separately authorized,
revision-safe and cost-bounded way to persist `strategy_state` and
replenish READY for measured outcomes. Existing legacy workflow writers
are not promoted to production automatically. Currently the continuous
metrics → attribution-preview → inventory-preview pipeline is implemented
in source and verified only by synthetic/offline tests.

## Production/VPS Operations handoff — DO NOT run from this chat

Prerequisites to be separately executed and evidenced by the common-VPS
Ops team and the owner:

1. Approve the *source-code release* and its destination; the repository
   is public and previous code export was stopped by an explicit review.
   GitHub Actions must not be started to deliver or validate this patch.
   The code in this phase is only on a local, unpushed branch.
2. Validate the actual immutable release symlink
   `BUFFERED_RUNTIME_ROOT/current -> releases/<40-hex SHA>`,
   release marker, `.venv/bin/python`, private mode-0600
   `shared/runtime.env`, and the existing shared deploy
   `/run/lock/chadult-production-deploy.lock`,
   Sheets quota lock and account locks. The wrapper holds the shared
   deployment lock while resolving the symlink to prevent release mixing.
3. Verify that **the existing GitHub Actions production aftercare schedule
   is disabled** and no other independent cron/workflow is still collecting
   or editing the same metric-jobs and metric-snapshots rows. This attestation
   is a human operational fact, not something the boolean proves by itself.
   Do not create a second writer while the Actions schedule remains live.
4. Using an authorized operator, establish separately verified
   Night/Liver Threads Insights read-scoped tokens and the current Sheets
   ACLs. Preserve user-specified account boundaries.
5. Run offline `--plan` followed by **explicitly approved, read-only**
   `--dry-run --confirm-readonly` in the production environment.
   Inspect the due-job list, age/window correctness, account identity,
   API quota and any preflight cancellations. Do not mark missing metrics
   as zero.
6. Only with specific write approval and the obsolete schedule disabled,
   set **both** protected flags in `runtime.env`, and perform a separately
   approved single-account manual canary with:
   `--account-id night_scout --apply --confirm-metrics --trigger manual`.
   After the run, independently check the exact
   `metrics_collection_jobs`, `metric_snapshots` and
   `posted_results` records. No second send on an unknown result.
7. If the canary, lock contention, timeouts, quotas, and rollback controls
   pass, Ops may install a limited, **Action-free** staggered system cron
   for the two accounts. The code does **not** install any cron. Timing,
   log rotation and interlock with the existing 5-minute publish cron
   require dedicated capacity planning.
8. Operational rollback is to **disable only this new aftercare cron and
   unset its independent write-approval flag**, preserve immutable
   snapshots/job attempts, and use the regular approved immutable
   release rollback. Never blindly remove metric rows or repost content.

Example **dry-run syntax** for Ops review (NOT executed):

```bash
CURRENT=/opt/github-runners/sns-growth-engine/.buffered-runtime/current
"$CURRENT/scripts/run_buffered_metrics_aftercare_host.sh" \
  --account-id night_scout --dry-run --confirm-readonly --trigger manual
```

The wrapper is intentionally **not** used for Beauty while
`AGENTS.md` and `GOAL.md` disagree on production scope. It does not
claim working production aftercare, completed metrics, or a working cron.

## Remaining required integration

This phase makes metrics collection runnable without Actions *once Ops
installs and approves it*, but does not complete the product loop.
Source result reservations must exist and be reconciled first.
Measured same-account attribution, `run_growth_attribution_cycle.py`,
`maintain_text_ready_inventory.py`, Gemini budgets, policy-controlled
content generation and verified next READY candidates are still separate
interfaces previously invoked via the aftercare workflow. Their
Action-free and cost-controlled staged rollout is the next appropriate
heavy integration. Real 24/72/168-hour observations take elapsed
time and cannot be replaced with mocks.
