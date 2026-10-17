# P0 Threads one-use ledger — read-only restore drill

**Purpose:** Test that a private P0 SQLite ledger with signed claim / attempt
history can be backed up to a fresh private temporary file and independently
restored into a second temporary file without modifying the operational ledger.
The source is opened in SQLite `mode=ro`, and all scratch backups are
immediately destroyed after validation.

## When to use

After the P0 private ledger has already been initialized and while the
production posting and P0 authorization switches are both **OFF**.

Use the owner-controlled manual GitHub workflow
`.github/workflows/p0-private-restore-readonly-drill.yml` on protected
`main`. It requires the literal confirmation
`READONLY_EPHEMERAL_P0_RESTORE`. The workflow runs on the existing
`sns-growth-xserver` self-hosted runner, with the private deployment lock
held in shared mode. It does not start cron, publish SNS, access Sheets or
create any operational backup.

For an authorized operator on the host, the equivalent command is:

```bash
python3 -B scripts/run_p0_host_restore_drill.py \
  --runtime-root /opt/github-runners/sns-growth-engine/.buffered-runtime \
  --confirm READONLY_EPHEMERAL_P0_RESTORE
```

The wrapper parses private `runtime.env` as data, **never** shells/sources
its contents, and never displays the private HMAC signing key, actual SQLite
path, queue identifiers, source text, provider IDs or URLs. If a partial or
malformed runtime state, lock contention, unexpected path, invalid signature,
send-attempt mismatch, restoration mismatch or file change is found, it exits
`BLOCKED` without touching the production ledger.

## What PASS does and does not prove

A green result indicates only that a read-only snapshot could be opened,
copied, its immutable HMAC event/send-attempt chains verified with the existing
key, a second SQLite copy independently restored, and source + restored
contents compared. The snapshot and restore are temporary; the tool **does
not leave a durable backup** or prove a host disaster recovery scenario.

Even on PASS the report keeps:
`durable_backup_retained=false`,
`operator_backup_restore_attested=false`,
`all_external_writers_disabled=false`,
`publish_authorized=false`,
`sheets_write_authorized=false` and
`production_cutover_authorized=false`.

For real disaster recovery, a separately authorized durable backup with full
latest signed journal, separately proven integrity/retention, and a real
restore/rollback drill are still required. Never revert to the initial empty
bootstrap backup after a real claim/send attempt, and never automatically
retry an ambiguous provider outcome.

## Offline test evidence

```bash
python3 -B scripts/test_p0_ledger_backup_restore_drill.py
python3 -B scripts/test_p0_host_restore_drill.py
```

These tests create fresh synthetic ledgers under private OS temp dirs. They
exercise claims, irrevocable send receipts, HMAC tampering, concurrent lock
refusal, alias paths, invalid secrets, no source modifications, source
metadata drift and a deliberately missing restore proof. They never read
real accounts or make provider calls.
