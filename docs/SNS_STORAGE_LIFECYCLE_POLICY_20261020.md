# SNS Growth Engine — Storage Lifecycle Policy
**Version:** 2026-10-20 JST. **Scope:** SNS Growth Engine only. This is not authorization to remove files or publish to social media.

## Owned assets and strict exclusions
SNS ownership is limited to /opt/github-runners/sns-growth-engine/ (dedicated runner and immutable runtime) and /var/lib/sns-growth-engine/ (dedicated user caches/state). The runtime shared/p0_once_private, credentials, Google Sheets data, P0 identity and rollback state are protected. The shared VPS deployment lock is /run/lock/chadult-production-deploy.lock; only VPS operations manages that common lock.

Global /var/lib/containerd, shared Docker/BuildKit images, /root, global package caches, other Chadult applications, other tenant databases and shared backups are OUT OF SCOPE. No blanket prune, global cache wipe, service stop or wildcard delete.

## Measured baseline: 2026-10-20 JST
All sizes are du -sk allocated KiB. Modification time is not proven last use.

| SNS-owned target | KiB allocated | Classification |
|---|---:|---|
| Immutable releases, 8 SHA directories | 4,452,212 | Rollback-sensitive |
| Current release | 737,624 | Protect |
| Previous release | 737,184 | Protect |
| Current isolated Python .venv | 720,152 | Protect |
| Runner _work (total) | 627,400 | Runner platform state |
| Runner _work/_tool | 583,392 | Regenerable, approval-gated |
| Hugging Face cache | 551,380 | Unknown offline dependencies, hold |
| pip cache | 82,980 | Regenerable, approval-gated |
| Dedicated runner diagnostics | 64,980 | Platform-managed, hold |
| Runtime shared | 16,300 | Protect |
| Runtime cron logs | 2,492 | Existing scoped rotation |
| P0 private ledger/recovery | 120 | Never auto-delete |
| Runtime user's .config | 75,368 | Protect user state and secrets |

VPS root was 82% used with 9,532,727,296 bytes free (~8.88 GiB). The existing pre-stage gate is 9 GiB and post-stage gate is 8 GiB: the former was BLOCKED by 130,949,120 bytes (~125 MiB). Never bypass this gate.

Exact live pointers: current=4ddab7079f70a844784be5aff9d049eb1b03eea2, previous=f6b78bacd6fa4a72d67894bd3c09cbac38391d99, pending=absent. Two of the eight SHA folders are only ~16 MiB and are not proven independently bootable releases.

Oldest unreferenced full release candidate: 2669c472afc3c4974fb495dd83b5d80464265b7e, last directory modification 2026-10-11, 732,580 KiB (~715 MiB). This is a preliminary review candidate, NOT deletion approval or proof of non-use. Confirm no hidden restore reference, scheduled job, active process or open FD before even considering a destructive change.

## Enforced release retention
1. Keep exact current and previous SHA pointers; never delete their releases.
2. Keep pending if it exists; unknown/ambiguous pending state blocks cleanup.
3. Keep an independent third FULL healthy SHA release as emergency rollback, with exact .production-release marker and executable isolated .venv, outside current/previous/pending.
4. Other releases have a minimum seven-day grace period, matching existing policy. Modification age alone does not prove unused. Malformed, partial, symlinked and unknown entries are protected until investigated.
5. Deletion requires the existing protected-main Production Capacity Recovery workflow, matching expected current SHA, one or two exact obsolete SHAs, explicit owner confirmation, shared deployment lock, reinspection under lock, live process/cwd/FD checks, and post-delete health/df review. Default is DRY_RUN. No automated release deletion is enabled.
6. Existing post-deploy stage cleanup is already limited to at most two old marked SNS-owned interrupted stages and seven-day age, under the global transaction lock. This existing narrow cleanup is preserved.
7. Do not deduplicate immutable Python environments via mutable symlinks to a shared venv. Existing pinning, --only-binary and PIP_NO_CACHE_DIR plus exact release revision allow clean rebuild attempts. Rebuildability and successful restore must still be tested before promotion.

## Cache, log and backup lifecycle
- Runner Python setup-python toolcache: the existing optional manual workflow enforces SNS ownership, 30-minute grace, at least 512 MiB recoverable, whitelist shape, global lock and process guard. It is never a daily deletion job. Confirm downloads/reconstruction are available before approval.
- Hugging Face models, pip, browsers, AI and media caches: measured, not cleared. An offline model or shared consumer may depend on them; prove producer/consumer and rebuild path before designing a time-to-live policy.
- Logs: preserve SNS-only cron logrotate (20 MiB per log, 5 compressed rotations). Dedicated Runner _diag remains platform-managed.
- P0 private DB/ledger, backups, media rights, original user uploads, tokens, passwords, customer data, service config and Google Sheets remain explicitly protected.
- Docker/containerd/BuildKit is operated by the common VPS team. No dedicated SNS Docker cleanup was established.

## Monitoring and deploy integration
The new scripts/sns_storage_lifecycle_audit.py performs exact-scope READ ONLY inventory. It validates immutable release SHA markers, root/pointer identities, executable isolated venv, seven-day candidate age, third emergency recovery environment, disk headroom and owned caches. It does not inspect file contents or change the system.

The new SNS Storage Lifecycle Read-Only Monitor workflow runs on the dedicated SNS runner daily at 02:45 JST, before the existing 05:15 media-preparation cron window. It uploads only a sanitized JSON inventory, retained 14 days, and emits warnings if the existing 9 GiB gate is blocked or total release size has increased versus the measured 2026-10-20 source-controlled numeric baseline. Trend is cumulative since baseline, not evidence of daily last-use.

After each successful immutable deployment, scripts/deploy_buffered_runtime_transaction.sh emits the read-only audit summary. Failed auditing causes a warning, not unsafe rollback or posting. No cron release deletion is enabled.

## Required approval and rollback procedure
Review daily audit, exact release SHA, current/previous/pending/emergency identity, age and rebuildability. Obtain explicit approval for each candidate SHA and conservative reclaim estimate. Run the existing Production Capacity Recovery workflow with exact current SHA and 1-2 targets, confirm_cleanup=false. Inspect dry-run identity plus process/FD/restore state, and only if separately approved rerun with confirm_cleanup=true. Re-measure root free bytes and SNS directory sizes and independently verify service health and the retained recovery layers. Stop on unknown outcomes. No human approval can be inferred merely from a DRY_RUN plan.

As of this initial audit: **actual bytes reclaimed 0**; potential oldest candidate ~732,580 KiB if independently approved. No database, shared Docker, Hugging Face or cross-service asset is authorized for deletion. Public SNS posting remains disabled pending separate safety and rollout acceptance.

## Separate READY acceptance problem
The 2026-10-20 six-hour Night Scout READY workflow run 39349595143 failed with QUALITY_EXHAUSTED. Underlying structured reasons include GENERATION_PROCESS_TIMEOUT, AI_APPROVAL_BUDGET_EXHAUSTED and no_hybrid_pass_candidate_for_exact_slot. Do not rewrite WAITING_REVIEW rows or bypass hybrid validation; successful measured READY needs a future scoped production verification.


## 2026-10-20 second verification — real disk gate and completed deployment

Owner-approved full-release cleanup removed only SHA 2669c472afc3c4974fb495dd83b5d80464265b7e under the shared deployment lock, using the same source-controlled process/cwd/FD scan with read permission elevated to VPS root. Reclaimed exactly 750,157,824 bytes (~715 MiB), with current/previous/emergency retained. The dedicated-runner attempt correctly failed closed with process_cwd_inventory_unknown and removed nothing; the privileged verified replay succeeded.

The newest source-controlled main SHA 4c162d5fb96168b2c88b8b58b40b8d918b3017dd then deployed with social posting OFF after passing the 9-GiB pre-stage gate. Its new immutable .venv again consumed most of the reclaimed space. Post-deploy independent SSH confirmed current=4c162d5..., previous=4ddab7079..., emergency=bec16989..., pending absent, posting OFF, P0 gate OFF, 0600 private environment, 3 account cron lines. The new release completed health and Sheets read-only verification. Do not claim permanent disk recovery; the future release-retention cycle remains approval-gated.

The existing media resource policy at config/media_growth_engine.json sets disk_prepare_stop_percent=80, independently of the staging free-space gates. The audit now reads that exact config and flags media-preparation status whenever used disk is >= the configured limit, even if a new release fits. The monitor emits a GitHub warning. This change adds no automatic deletion and is deployed through the GitHub-hosted audit workflow without staging another 720-MiB immutable runtime.
