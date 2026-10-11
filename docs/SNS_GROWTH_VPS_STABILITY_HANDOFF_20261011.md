# SNS Growth Engine — VPS stability / deployment handoff

Date: 2026-10-11 JST. Scope: `dev-ch-hhuk39/sns-growth-engine` only.

## Confirmed facts and owner boundaries

- Shared VPS `x85-131-249-42` at 14:13 JST: approximately 14 GiB free (73% usage), 1.9 GiB total RAM, 600 MiB MemAvailable, ~933 MiB Swap used.
- The production SNS pointer remains `994553dfc1faf644784c72bf97201b2cee927c9d`. Repository main at inspection was `e92a67daa2c39d64b5271cc944e410bbd012f533`. They are not synchronized.
- October 1–2: SNS `snsrunner` cron Python was OOM-killed at approximately 1.1 GiB RSS, while unrelated Renewal HP Next.js also experienced OOM. No later OOM kills were reported by shared VPS operations after October 3.
- Three SNS accounts have independent five-minute schedules. Heavy media acquisition/transcription begins at 05:15 JST on VPS; a GitHub-hosted media fallback is scheduled at 10:45 JST. Both preserve rights, quality gates and READY identity; hosted replenishment is not itself evidence of live-ready media.
- The shared host's Docker, databases, other services, backups, log controls and global resource limits are owned by the cross-service VPS Ops function, not SNS.

## Source changes staged in draft PR (NOT deployed)

1. `scripts/check_chadult_vps_deploy_preflight.sh`: fail closed through `sudo -n /usr/local/sbin/chadult-vps-resource-check --preflight 8`. Uses the shared 8 GiB minimum, 384 MiB available RAM and below-88% disk policy. Does not reduce shared thresholds.
2. `scripts/install_buffered_production_runtime.sh`: stage-only immutable release construction with no implicit activation; a separate scheduler-only mode after verified promotion. Builds only binary wheels, no pip cache or bytecode compilation; an owned `.stage-*` is removed on catchable failures/signals. The unbounded venv build on VPS is reduced but not fully moved off-host.
3. `scripts/deploy_buffered_runtime_transaction.sh`: requires a pre-existing globally owned `/run/lock/chadult-production-deploy.lock`, acquires exclusive lock, rechecks resources, stages 0600 candidate secrets, installs release and checksum-pinned CLI, verifies candidate dependencies and read-only Google Sheets connectivity with bounded retries, atomically updates `current`, rechecks health, installs 3-account cron, and records `previous`. On failure after activation, restores old `current`, environment and cron and re-verifies prior health; failed rollback verification is reported CRITICAL.
4. `scripts/run_buffered_production_host.sh`: retains independent account locks and serialized Sheets I/O, plus shared lock participation and a minimum 512 MiB available host RAM gate. Never posts when the runtime's posting switch is disabled; X remains OFF.
5. `scripts/run_buffered_media_preparation_host.sh`: on hosts below 4 GiB total RAM or 1.5 GiB MemAvailable, defers heavyweight media acquisition/transcription to existing GitHub-hosted fallback rather than risking cross-service OOM. No fake READY records or text substitution. Takes the shared lock when media processing actually runs.
6. `scripts/prune_obsolete_runtime_releases.py`: recognizes explicit `current`, `previous`, and `pending` pointers rather than guessing rollback from latest modification time. Retention requires ≥7-day age, explicit approval, and scoped paths; uses shared lock and in-use detection. No VPS release was removed.
7. `scripts/cleanup_owned_sns_deploy_stages.py`: after a successful deploy, may remove at most two ≥7-day-old interrupted install stages containing the exact SNS-owned marker and not referenced by protected pointers; cannot delete other directories/releases.
8. SNS-only cron logrotate configuration caps each `.cron.log` at 20 MiB with five compressed rotations; shared host logging is not altered.
9. Offline normal/abnormal simulations cover preflight refusal, timeout, failed health before/after switch, cron failure, missing/busy lock, old runtime restoration, rollback-health failure escalation, scoped stage cleanup, secrets file mode and candidate retention.

## VPS administrator prerequisites (not authorized for SNS to alter)

- Grant only `snsrunner` narrowly scoped passwordless invocation of the exact shared command `sudo -n /usr/local/sbin/chadult-vps-resource-check --preflight 8`. At inspection it was `root:root` mode 0750 and `snsrunner` invocation requested a password. Verify the actual sudoers rule before activation.
- Create and govern `/run/lock/chadult-production-deploy.lock`, including permissions/group, cross-tool convention and restart behavior. At inspection this path did not exist. Other services must participate in the same lock; SNS will not create another global lock.
- Ensure `/usr/sbin/logrotate`, `flock`, `ffmpeg`, `xvfb-run` and package binary-wheel prerequisites are installed on the host. Check version compatibility rather than replacing shared binaries.
- Move any remaining large dependency build/model work to a separate runner or container with enforced memory limits. A shared 1.9 GiB host is not sufficient for simultaneous heavy Python and Next.js workloads; pip binary-wheel restriction is a partial mitigation, not a completed off-host build migration.
- Preserve all shared backups/DB, Docker layers, media caches and other services. SNS source changes must never run `docker system prune`.

## Production promotion runbook (only after Ops prerequisites and CI)

1. Confirm full CI PASS, independent live backups and recovery ownership, and latest current/previous/pending pointers. Restrict input ref to main and default `posting_enabled=false`.
2. Verify shared `sudo -n` preflight from `snsrunner` and shared lock mode; remeasure host memory and disk immediately before deploy.
3. Dispatch `Deploy Buffered Production Runtime` on main with explicit confirmation. It performs a single lock-protected transaction, checks Sheets read-only and dependency metadata twice, and atomically promotes. Avoid a second concurrent service deploy.
4. Verify the installed SHA, cron entry uniqueness, three-account no-post dry-run evidence, resource dashboard and logrotate. The pure health check is infrastructure readiness, not proof of commercial READY inventory or Threads actual posting.
5. On post-promotion error, expect automatic pointer/env/cron rollback and health verification of the prior release. Exit status 90 denotes rollback verification failure and demands immediate human investigation; do not retry blindly.
6. Dry-run SNS-only release retention with explicit current SHA, manually review any candidates (especially unfinished/pending), then use the protected confirm path only when eligible.

## Test and rollout boundaries

- Unit/simulation tests can verify transaction ordering and fail-closed behavior without production posting; GitHub CI and the real self-hosted runner still need confirmation.
- Real failure drills (disk pressure, memory pressure, Sheets failures, late health, interrupted build, unsuccessful rollback) must not be injected into the shared production host. Run them on an isolated disposable Linux fixture or throwaway VPS.
- No live posting, no rollback operation on production, no shared Docker change and no deletion of operational assets were performed while authoring this branch.
- The finished code remains in a Draft PR until shared VPS access and cross-service lock prerequisites are met. A verified production deploy is a separate gated acceptance step.
