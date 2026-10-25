# SNS Growth Engine — VPS-first operations migration (2026-10-25 JST)

## Verified completed work
- Existing Ubuntu unattended-upgrades, UFW, fail2ban and shared R2 backup/restore health confirmed. Shared VPS root stayed about 79–81% full during work.
- Exact SNS-only obsolete immutable release `bec16989c859e97abe53a736afb6d76bc12338a1` was removed via the verified guarded Python pruner, after current/previous/third emergency proof, process/FD/mount/owner checks and the global lock. **754,872,320 bytes reclaimed**. Other applications and recovery pointers unchanged.
- Shared R2 restic wrapper's erroneous default `--apply --with-prune` changed to `--apply` **on VPS**. Before mutation, `--audit` validated 358 snapshots / 55 cohorts, 227 logical candidates. Actual `--apply` safely returned `DEFERRED_BUCKET_LOCK`, proof_unknown=0: zero deletions because R2 enforces 7-day object locks. Capacity audit retried PASS. Never run raw R2 object deletes or unsafe `restic prune` against protected shared pack/index files.
- Cloudflare account-level metrics: Standard published 7.12 GB, 32,545 objects, 10 R2 buckets. This is a point-in-time measurement, not a monthly zero-cost guarantee. R2 free Standard threshold is 10 GB-month; track storage and operation usage.
- Installed daily SNS-only local security/backup service (`sns-growth-local-security-health.timer`, 08:30 JST). First run 12/12 PASS.
- Installed no-write 3-account READY audit (`sns-growth-local-ready-audit.timer`, 02:10/08:10/14:10/20:10 JST). Direct Sheets-backed result: Night 3/3, Liver 3/3, Beauty 1/1 verified, no posts/writes.
- Installed hourly SNS-only missed-slot read-only local audit (sns-growth-local-missed-slot-audit.timer, hourly minute 13 JST). First run: Night+Liver PASS, Beauty verification temporarily unavailable. Root cause was not proven; retry of Beauty individually PASS, subsequent complete three-account run PASS (each account 1/1, writes=0 posts=0). Disabled content-slot-recovery.yml only after fully verified VPS replacement. Manual write recovery remains possible only via the separately protected VPS reconciliation gate, not automatic local audit.
- Installed OSV dependency scanner (`sns-growth-local-dependency-audit.timer`, 03:20 JST). Initial scan of 79 installed Python packages found 3 advisories on setuptools **79.0.1**; GHSA-h35f-9h28-mq5c, GHSA-xmj3-9gf7-h52w and PYSEC-2026-3447. OSV check of **84.1.0** returned zero advisories; this version is pinned **for a future freshly-built immutable runtime only**. Current release still has the old dependency. No production mutation.
- Installed SNS-only weekly old Chrome crash telemetry cleanup (`sns-growth-local-chrome-cleanup.timer`, Sundays 06:23 JST). Dry-run and apply returned PASS, removed 0 files, scope strictly bounded to old owned diagnostic dumps.
- Added 02:45 read-only SNS immutable-release audit to the existing 18:25 local retention timer. Verified local audit status PASS, removed 0, preserves 7-day and three-rollback policy.

## GitHub Actions transition (no CI Actions run intentionally during this task)
- `sns-storage-lifecycle.yml` was disabled only **after** the VPS read-only audit matched and passed.
- `sns-chrome-crash-diagnostics-lifecycle.yml` was disabled only **after** the VPS cleanup service passed.
- The remaining 18 originally scheduled workflows have **NOT** all been migrated. A GitHub workflow that writes Sheets, generates content, publishes, analyzes metrics or changes credentials must be replaced with an equivalent authenticated VPS job, serialized locks, bounded budget, logs, no-post gates and a verified recovery path *before* disabling. Do not treat simple read-only coverage as a replacement for publishing.
- The existing protected `main` requires GitHub `pr-gate`. This local branch is pushed but is NOT merged. Disabling CI or forging a status to bypass branch protections is forbidden; work continues on the traceable feature branch until an approved merge path is chosen.

## Outstanding acceptance
- Google Sheets bank 30/30 verified for all 3 accounts, not just next-24h READY; historical VALIDATED bank rows require canonical account/slot, unallocated queue, publication safety, hashes and runtime checks. Do not force-approve.
- Actual Threads first canary, owner-signed per-account release, irreversible ledger proof, then 24h/72h/168h observations. **Posting remains OFF**.
- Media source asset availability/rights and upload proof, Aftercare success across all 3 accounts, full scheduled-workflow migration, Sheets restoration of native metadata/permissions, validated R2 pack/index prune policy after object lock expiry.
- Do not upgrade live immutable site-packages in place; pending setuptools fix is only in the next build script. Confirm disk headroom before staging: a new ~700MB isolated release could push root back over the 80% media safety threshold.
