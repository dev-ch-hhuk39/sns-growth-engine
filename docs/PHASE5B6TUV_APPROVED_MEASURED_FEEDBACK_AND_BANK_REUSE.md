# Phase 5B-6T/U/V — Source-only measured-strategy and zero-AI READY reuse

Date: 2026-10-13 JST. **Mac local-only implementation. Not pushed,
merged, deployed, provisioned, scheduled or executed against production.**

## What this batch closes

6Q added an Action-free Threads metrics-aftercare host; 6R/6S attached
read-only attribution and READY inventory inspection. This batch
**reuses those existing scripts** and adds two separately authorized
**manual-only** write stages to the same bounded aftercare runner:

1. **Measured attribution and bounded strategy-state persistence**
   (`--with-strategy-apply`).
2. **Reallocation of already approved evergreen READY text candidates only**
   (`--with-ready-bank-reuse`), with `--max-bank-allocations 0..6`,
   default two, across the single account's entire invocation.

There is **no new deployment scheduler, DB, API integration, AI service,
media processing, browser automation, background ChatGPT task or SNS
publisher**. GitHub Actions remain unused. The existing Night/Liver
account split is preserved; Beauty remains ineligible for this host.

## Default and consent boundaries

`run_buffered_metrics_aftercare_host.sh --account-id night_scout --plan`
is *fully offline* and requires no credentials. The optional
`--with-feedback-preview` adds two pure read-only stages to an
otherwise separately authorized real metrics inspection.

**Either write stage is rejected before reading the runtime config unless
all of these are true:**

- one approved named account, `night_scout` or `liver_manager`;
- `--apply --confirm-metrics --trigger manual` (not a cron invocation);
- the existing common production deploy, shared Sheets quota and
  per-account locks and pinned immutable release are available;
- the protected mode-0600 `runtime.env` explicitly declares
  `AFTERCARE_METRICS_WRITE_APPROVED=true` and
  `AFTERCARE_ACTIONS_DISABLED_ATTESTED=true`;
- `--with-strategy-apply` **additionally** requires
  `AFTERCARE_STRATEGY_WRITE_APPROVED=true`;
- `--with-ready-bank-reuse` **additionally** requires
  `AFTERCARE_READY_BANK_REUSE_APPROVED=true`.

All four values are removed from the caller environment before sourcing
the owner-managed runtime config. **These flags are operational attestation,
not evidence of real IdP login, approval by two people, or that GitHub
Actions were actually disabled.** The separate VPS Ops/owner must verify
those facts. If an approval flag is absent, the optional stage is blocked.
A cron run cannot opt into the write stages even with stray flags.

The shared deploy lock pins the release, and Sheets/account locks remain
held for the entire authorized metrics → strategy → bank-reuse → optional
read-only-preview chain. This avoids in-wrapper time-of-check drift; it
does not make Google Sheets and other systems atomic.

## Stage 1: measured strategy

`run_growth_attribution_cycle.py --account-id <exact account> --apply
--confirm-attribution --use-sheets --max-write-rows 120` reuses
`src/learning/feature_attribution.py` and its source-backed 24/72/168h
results.

- Requires at least one **measured, verified** observation. A missing
  measurement is not interpreted as 0 or permission to learn.
- Hard combined cap of 120 attribution + strategy rows per invocation
  in this host; standalone CLI cap can be changed only between 1 and
  500 with an explicit argument.
- No write to `queue` or `posted_results` schema; only the **already
  existing** `post_attributions` and `strategy_state` tabs are
  eligible. Missing tab/columns are a blocker, not auto-migration.
- Global key uniqueness, exact account, column/schema compatibility and
  stable IDs are checked. Identical rows are skipped. Existing
  `post_attributions.created_at` is preserved, and unchanged strategy
  evidence does not rewrite `updated_at` solely because time passed.
- Writes use **RAW** Google values, preventing external text beginning
  `=` from being interpreted as formulas.
- A post-write readback must find exactly one row with matching data for
  each changed ID. Partial writes, network timeouts, bad readback or
  missing Sheets become `OUTCOME_UNKNOWN_BLOCKED` / non-zero exit.
  **No automatic retry**. This host aborts subsequent write stages.

**Important limitation:** operational Google Sheets row updates are not
atomic with one another or with local SQLite. This is a legacy
account-scoped writing path, **not the SQLite single-source-of-truth
migration**. An incomplete first-tab write can remain after a later
failure. Read-only evidence inspection and an operator-approved
reconciliation are mandatory before another attempt. It is not a
general exactly-once integration or a replacement for the more
sensitive two-human/media authorization stack.

## Stage 2: READY bank reuse without paid AI

`maintain_text_ready_inventory.py --account-id <exact account> --apply
--confirm-ready-maintenance --use-sheets --reuse-only
--max-bank-allocations 2`

- Uses the existing `evergreen_inventory.allocate_bank_candidate`
  procedure and its publisher/source/hybrid safety validator.
- Requires an **existing** evergreen bank tab. No tab creation or schema
  migration in reuse-only mode.
- **Never calls `replenish()`, `replenish_bank()`, an external AI
  generator or media generation**, even when no valid candidate is
  available. This is a hard code branch, with synthetic tests that
  fail if a generator is called.
- At most 0–6 previously approved allocations **across all slots for
  one account, per invocation**, default 2. Zero means a no-allocation
  canary. Any write is still subject to the existing read-after-write
  and eligibility checks of the bank allocator.
- If no candidates satisfy the source rights, slot account and READY
  rules, return a shortfall and non-zero exit, rather than claim
  a complete delivery. Do not retry failed or uncertain writes
  blindly.

This stage uses **zero paid content-generation calls**, but Google Sheets
reads/writes and the existing Threads metrics collection may consume
provider quotas. This is not a total zero-external-API guarantee.

## Full stage order

If and only if separately enabled for a **manual** canary, the host
will perform, under the same pinned-release and quota/account locks:

1. Existing metrics **read-only plan**.
2. Existing approved metrics collection `--apply` (up to 20 due jobs).
3. Optional measured strategy update. The protected operational flag
   attests approval and the CLI validates account scope and evidence;
   it does *not* implement a new IdP signoff.
4. Optional zero-AI READY bank reuse with separate operational flag.
5. Optional read-only attribution + READY coverage previews.

Every live read/write can fail. A later failure does **not** roll back
already acknowledged prior stages and must be examined manually;
there is no automatic retry. The host never publishes text, video,
carousels or media, and explicitly disables expensive content
generation and upload flags.

## Offline validation (safe on Mac)

```bash
bash scripts/run_buffered_metrics_aftercare_host.sh \
  --account-id night_scout --plan --with-feedback-preview
python3 scripts/test_measured_feedback_write_safety.py
python3 scripts/test_buffered_metrics_aftercare_host.py
python3 scripts/test_action_free_feedback_cli_gates.py
python3 scripts/test_feature_attribution_cycle.py
python3 scripts/test_ready_inventory_maintenance_contract.py
python3 scripts/run_local_quality_gate.py --mode full
```

These tests use temporary synthetic rows, mock Sheets and injected fake
workbooks; they do not exercise real IdP, Google Sheets, deployed cron,
SNS Insights, or production postings. Shell syntax and static
GitHub workflow files can be inspected locally; **GitHub Actions CI must
not be dispatched**.

## Unfinished, authorization-gated work

- The real **common VPS** remains owned by the separate Ops chat.
  It must provision the release, inspect the immutable symlink,
  perform backups and migrations, confirm the old Actions
  aftercare schedule is disabled, and assess permissions and concurrency.
- Real metrics/strategy/READY writes require independent owner approval,
  read-only preflight, a small **manual** canary and reconciliation of
  actual Google results. This development has done none of these.
- If future cron automation is desired for strategy or bank reuse, it
  needs new operational approval, source-of-truth reconciliation,
  quota-aware scheduling, durable unknown-outcome audit and rollback.
  Simply passing the flags to cron will not work.
- Paid, new-content generation is **not** enabled. The owner must
  separately approve a nonzero actual generation budget and candidate
  rights/review rules; no invented dollar limits or calls are used here.
- Old Sheets writers and new SQLite protected writer still require
  a real source-of-truth cutover; physical-media publication remains
  under independent rights/approval blocks.
- Beauty production activation and true multi-account operational
  proof are outside this batch.
