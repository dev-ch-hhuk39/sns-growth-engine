## 2026-10-16: host launcher/deploy integration (local code only)

The immutable VPS text launcher now defaults posting OFF when its runtime
posting switch is absent. Even with BUFFERED_POSTING_ENABLED=true, real apply
is restricted to night_scout/liver_manager and requires
SNS_P0_ONCE_GATE_ENABLED=true plus a successful read-only
scripts/validate_p0_once_runtime.py check BEFORE Sheets, scheduling or
provider invocation. It verifies the private SQLite file, all signed event
chains and every immutable send-attempt MAC. Protected media and Beauty
cannot use this text-only send authority.

The transactional deploy candidate writer now inherits ONLY the host-local
P0 gate, private SQLite path and HMAC key from an existing owner-only 0600
runtime.env/backup under the VPS global lock. Inbound CI/GitHub variables
CANNOT overwrite these values. An attempted posting-enabled deployment
without a locally configured P0 authority fails/rolls back. A deploy with
posting disabled may stage code without enabling traffic.

Release operations NOT performed here: host/owner-attested sole-writer
custody, authoritative Google Sheets writer inventory shutdown and snapshot,
verified backup+restore, production HMAC/DB provisioning, protected account
credentials, real Night/Liver canaries, Sheets readback, timed 24h/72h/168h
metrics, feedback and media rights. No VPS operations, public pushes,
provider calls or real Sheets mutation were executed. A green Mac test suite
is only CODE ACCEPTANCE; it is not a GO decision for production.

## 2026-10-16 implementation update: one-use enforced at HTTP sink

The code-level text-only Threads sender now requires an authenticated existing
SQLite CLAIM before making either actual Threads HTTP POST. The permit is scoped
to the exact account, queue, public text and an immutable HMAC-chain event.
The first container request atomically inserts a signed, immutable one-use
send-attempt record (same local SQLite DB) before network I/O; a second attempt
cannot reuse that row even across processes or after a crash. This is NOT a
remote platform idempotency key.

When SNS_P0_ONCE_GATE_ENABLED is OFF (the default), real processing refuses
BEFORE writing PROCESSING to Sheets; dry-run and local generation remain
available. All previously separate direct Threads CLI outbound is blocked.
The real HTTP sender requires a real P0OnceGuard class, not arbitrary fake
objects or boolean flags. Source code, not local environment flags alone,
enforces this precondition.

New databases contain sns_p0_once_send_attempts and immutable triggers.
An older existing database missing these protections will FAIL CLOSED rather
than being silently migrated/recreated. Do not replace an operational ledger.
No live account, queue migration, host/IdP custody, signing-key deployment,
media publication, production Sheets write, GitHub push or canary was executed.

These are local engineering changes only. Approval of the single operational
host, external writer disconnection, backups/restore, authenticated sources,
account canaries and metric/PDCA production proof remain mandatory.

---

# SNS Growth Engine | One-use barrier in the actual Threads TEXT provider path

Date: 2026-10-14 JST. Intended Mac code base: `e36c0b89636477ff8415ee14116d3a7887289efd`, branch `chatgpt/sns-completion-local-noactions-20261013`.

## The concrete problem being addressed

`process_threads_queue.py` currently writes `PROCESSING` to Google Sheets, reads the row back and then sends a Threads API request. This is not a distributed compare-and-swap; two concurrent workers can both believe they own the same post. The previous local `p0_queue_cas_rehearsal.py` only simulated claims and never governed the actual publisher call. This patch adds an **optional, durable, single-machine send claim** immediately before that actual call; it is not another blocked rehearsal.

## What changes in the real worker

- The operator-controlled flag `SNS_P0_ONCE_GATE_ENABLED` defaults to false. No posting flags, workflows, schedules, Secrets, credentials, accounts, provider calls or deployment are enabled or changed by the installer.
- If opted in after an authorized release review, `P0OnceGuard.from_env()` verifies that an existing private operational SQLite file and HMAC signing key are available **before** the Sheets `PROCESSING` write. The ledger is **never auto-created** during the publish path.
- After existing Sheets `PROCESSING` readback, a SQLite `BEGIN IMMEDIATE` transaction claims a globally unique queue ID with the SHA-256 fingerprint of the exact public text and account ID. There is **no claim lease expiry** and no automatic claim release.
- A second process claiming the same queue ID, **the same exact text for the same account even under a different queue ID**, changed source hash or wrong account is blocked before it reaches `ThreadsPublisher.publish(..., dry_run=False)`.
- The provider ACK (including external post ID) is recorded in an HMAC-chained immutable SQLite event **before** writing the Google Sheets posted-result. If the result is unknown, an uncertain state is retained; **no automatic resend** is allowed.
- Final `POSTED_VERIFIED` is emitted by the ledger only after independent readbacks of exactly one matching queue `POSTED` row and exactly one matching posted-result row with the right account, text, provider ID, `real_post=true`, `verification_status=READ_AFTER_WRITE_PASS` and Threads platform. A Sheets failure or missing ACK leaves a non-retryable reconciliation state.
- Only Night Scout (`night_scout`) and Liver Manager (`liver_manager`) **text-only** are in this additional gate. A media/Beauty attempt is blocked when the gate is enabled; existing media publish stops and X-disabled policy remain unchanged.

## Safety guarantees and *important limits*

This code prevents two cooperating processes on a **single trusted host using the exact same SQLite database** from both claiming the same queue ID. Its SQLite uniqueness and on-disk journal are meaningful but are **not a distributed lock across separate hosts**, a guarantee against writers that bypass this module, or proof that a provider idempotency key exists. The current frozen 6H inventory lists historical direct Sheets mutation sites and cannot prove they have all stopped. A direct Threads publisher called elsewhere can bypass this specific worker integration. Before activating it, the operator MUST prove all sending workers use the same host/DB and that no other external sender or direct SNS entrypoint remains.

The queue source of truth **remains Sheets**. No real Sheets rows are migrated by this patch. This is not permission to cut over to SQLite, an attested source export, human/media rights approval, a canary, or production rollout acceptance.

SQLite claim journaling cannot atomically commit a remote Threads POST and a Google Sheets write. On a crash between claim and provider request, the claim remains blocked even if no post was sent; on a crash between the API and ACK persistence, provider outcome may be unknown. **This design intentionally favors manual reconciliation over risking a duplicate.** Never clear, delete, overwrite, silently rotate, or rebuild an operational ledger to get past a blocked queue.

## Operator-only activation prerequisites (NOT done by this patch)

1. Freeze and discover all live publishers, other hosts, cron and schedules; demonstrate a single authorized sender and that the ledger is on a persistent **local, owner-controlled non-network filesystem**. Verify that every real sending path passes this ledger or is disabled.
2. Finish source/posted-results reconciliation and a verifiable provider-scoped identity, app permission and Sheets source snapshot. Verify no unsent records are already posted and reconcile ambiguous outcomes by provider readback.
3. Take a recoverable production backup and perform a separate restore drill. Have a recovery plan that **preserves claims even after DB loss**. Use one stable secure HMAC key stored outside the repo; restrict DB file mode to 0600, directory owner-only/non-group-writable. Never print/log the secret.
4. Test real publish-time public text, media rights, account/persona and provider identity. Existing Beauty and all media remain out of this one-use path.
5. Only after owner/operator approval, explicitly configure the matching `SNS_P0_ONCE_DB_PATH` and `SNS_P0_ONCE_HMAC_KEY_HEX` through the approved runtime secret facility, plus `SNS_P0_ONCE_GATE_ENABLED=true` in the **single allowed Threads worker**. Existing `PUBLISH_ENABLED` / `ALLOW_REAL_THREADS_POST` and `--confirm-real-post` remain independent permissions. Do not enable these in this implementation session.
6. Use a bounded provider-approved real canary and independently verify queue/results/provider ID/URL, monitoring, recovery and measured 24h/72h/168h feedback. Until all are proven, `production_cutover_authorized=false`.

## Maintenance examples — DO NOT RUN AS PART OF THE LOCAL INSTALLER

The following are **operator steps after backup/permission approval**. The CLI has no post/send/cutover commands.

```sh
# Only after owner approves local ledger custody and its permanent location:
python3 scripts/p0_real_delivery_once.py init \
  --db-path '/absolute/permanent/operator-owned-directory/p0-once.sqlite3' \
  --explicit-operator-init

# A read-only queue inspection requires the already managed runtime signing key.
# Never paste that key or its environment value into ChatGPT or logs.
python3 scripts/p0_real_delivery_once.py inspect \
  --db-path '/absolute/permanent/operator-owned-directory/p0-once.sqlite3' \
  --queue-id 'your_existing_safe_queue_id'
```

`init` only creates an empty ledger and returns `LEDGER_CREATED_NOT_ACTIVATED`; it cannot authorize posting, migrate historical queue identities, or safely recover a lost DB. If the ledger may have ever been active, do not run `init` to replace it.

## What is tested independently

- Concurrent claims from two SQLite connections, duplicate queue across accounts, changed content digest, signed journal and tamper detection, permissions, symlink/missing DB, only-once source operation, same-text different-queue denial, missing provider ACK, unknown outcome, terminal states, unique external post ID and two-source readback requirements.
- Synthetic worker integration tests exercise opt-in OFF, dry-run isolation, env/preflight failure before Sheets writes, provider failure, ACK persistence before result save, duplicate worker denial and final queue-result mismatch. No real credentials or outbound network are used.
- The actual Mac integration script adds the implementation to the existing worker, runs full repository QA and security checks, then commits locally. If source anchors drift or tests fail, it blocks/rolls back rather than bypassing the guard. It does **not** enable the feature or claim source-of-truth cutover.

## Completion status

- Local code development can be marked complete only after the Mac installer returns `LOCAL_P0_ONE_USE_INTEGRATION_COMPLETE` and the full local QA report passes.
- `source_of_truth_cutover`: NOT DONE.
- `all_legacy_and_external_writers_disabled`: NOT VERIFIED.
- `provider_one_use_gate_activated`: FALSE.
- `production_canary`: NOT RUN.
- `automatic_media_posting`: NOT APPROVED.
- `production_automation`: NOT ACCEPTED.
