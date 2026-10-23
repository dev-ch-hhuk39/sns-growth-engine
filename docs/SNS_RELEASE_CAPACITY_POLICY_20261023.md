# SNS Growth Engine VPS capacity retention decision (2026-10-23)

Owner authorized aggressive removal of obsolete SNS-only immutable release
directories after the move to R2 for operational backups. Previously, 15
immutable versions occupied about 9.2 GiB on a 49 GiB shared VPS; the
seven-day grace made the daily retention timer a no-op.

Policy update:
- Hold all referenced current, previous, and pending releases.
- Hold the newest independently bootable third rollback and the existing
  pinned emergency release. Never delete those even if older than a day.
- Permit release directories older than 24 hours only when exact 40-hex
  SHA identity matches a tiny, exact .production-release marker.
- At most four candidates per individual locked invocation. Daily timer
  uses this policy; a separate human-approved invocation can repeat.
- Check successful, recent shared R2 backup AND health service, enabled
  backup timer, and bootable rollback targets before invoking the pruner.
- Under a nonblocking shared deployment lock and an SNS-only capacity
  lock, revalidate current/pending/previous, all live process cmdlines,
  cwd, file descriptors, node ownership, symlinks, hardlinks and mounts.
  An unexpected entry or foreign owner blocks deletion.
- Deletion is limited to
  /opt/github-runners/sns-growth-engine/.buffered-runtime/releases/<sha>.
  Shared environment, runtime data, backup manifests, queues,
  data ledgers, other applications, Docker and R2 are never touched.

Releases are reproducible build artifacts from GitHub, not equivalent to
R2 state backups. A recent R2 backup job success does not prove
restoration of every old Python venv; source history and retained bootable
rollback versions are separate recovery layers. No backup-restore
success is inferred solely from retention or R2 health service status.

Operational verification: local synthetic tests, production dry-run
inventory, recent offsite backup/health, exact candidate SHA checks,
then manual guarded apply. Report the real disk before and after.
If in-use / ownership / mount / backup / shared-lock checks fail, stop
without trying a bypass or changing other application files.
