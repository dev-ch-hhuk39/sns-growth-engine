# SNS Growth Engine / Chadult VPS stability handoff (2026-10-11 JST)

## Verified operating boundary

- The shared host is `x85-131-249-42`. At 14:02 JST: root filesystem 73% full, roughly 14 GiB free, MemAvailable 524 MiB, and 949 MiB swap used.
- The GitHub Actions self-hosted SNS runner is `snsrunner`; its runtime is rooted under `/opt/github-runners/sns-growth-engine/.buffered-runtime`.
- `current` points to release `994553dfc1faf644784c72bf97201b2cee927c9d`; previous release `9ec1deee6848fad68f754d241ce6ca9792d269af` is retained. Do not delete either or any staged candidate without renewed verification.
- The three account production cron jobs run every five minutes with offsets of 0, 1 and 2 minutes. Media preparation starts at 05:15 JST daily with a 270-minute outer timeout.
- September 30 to October 2 kernel OOM entries killed `snsrunner` Python children in the cron service (roughly 1.1 GiB RSS) while also killing unrelated Next.js services. No new OOM kills after October 3 were reported by shared VPS operations. The command line of the killed historical processes remains unconfirmed.
- Media preparation already has a dedicated lock, bounded child timeouts, temporary-workspace cleanup on normal exit and provider cleanup in `finally`. The account publisher has separate account locks plus a Sheets I/O lock. These do not implement a cross-service deployment lock.
- The October 7 buffered runtime deploy failed at the post-switch no-publish verification step. The installer currently changes `current` before that verification, and does not roll back automatically. Fix before any production switch.

## Phase 2A source-only changes

- `scripts/check_chadult_vps_deploy_preflight.sh`: fail-closed call to the root-owned shared resource gate; requires at least 8 GiB free, shared MemAvailable >=384 MiB, and filesystem use below 88%.
- `deploy-buffered-production-runtime.yml`: gate runs before the secret environment is written and before release installation.
- `install_buffered_production_runtime.sh`: direct installer cannot bypass the gate; its own incomplete `.stage-${REVISION}.XXXXXX` is cleaned on ordinary exit, INT or TERM without touching installed releases.
- Offline unit tests cover resource denied, argument validation, stage failure, protected current/rollback, and workflow ordering.

## Required shared VPS administrator work — NOT performed by SNS team

1. Allow only `snsrunner` to invoke `sudo -n /usr/local/sbin/chadult-vps-resource-check --preflight 8` without a password. The executable is currently `root:root` mode 0750 and runner sudo fails. Use a narrow, audited sudoers entry rather than unrestricted sudo. If a future deployment needs more than 8 GiB, coordinate a correspondingly narrow allowance.
2. Specify the ownership/mode/creation mechanism and acquire/release protocol for `/run/lock/chadult-production-deploy.lock`. The path was absent during inspection. The global lock must wrap resource preflight, release construction, activation, health verification and rollback across all tools. Do not create an independently owned lock in SNS.
3. Align peak-memory and build scheduling: `snsrunner` media preparation was involved in past global OOM events. Heavy video/model work and dependency builds should move to an isolated runner/host. The global minimum MemAvailable 384 MiB is not proof that a heavy job fits on this 1.9 GiB shared host.

## Remaining SNS implementation before a production deploy

- Move expensive clip acquisition/transcription/media preparation off the shared VPS without bypassing rights gates, idempotency, or READY verification.
- Install an immutable candidate without switching; validate dependencies and dry-run health against the candidate; atomically switch with a recorded previous pointer; on failure restore the previous release and verify health again.
- Add conservative SNS-only retention for current, previous and pending release, plus expired `.stage-*` cleanup only after checking age, ownership and active processes.
- Add bounded memory/parallel execution and workload-scoped locks for heavy media work, and verify failures including disk/RAM shortfall, delayed health, rollback failure and SIGKILL after-stage artifacts.
- Keep all cross-service Docker, DB, backup, host log, service-resource and lock administration outside SNS source control.

## Production safety gate

This source branch is NOT deployable while the shared gate runner permission, common lock, post-switch rollback and no-post health evidence remain unresolved. Do not disable validation, auto-post X, broaden permissions, or delete shared resources to bypass them.
