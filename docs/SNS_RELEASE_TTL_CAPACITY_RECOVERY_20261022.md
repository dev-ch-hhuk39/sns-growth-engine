# SNS-only safe retained release reclamation

A new SNS-specific **root-owned** systemd service/timer executes at 18:25 JST
each day, starting after the first seven-day grace expires on October 23, 2026.
This is not a CI pipeline or a change to other services' systemd units. The
source is kept in the public SNS repository; its installed production copy and
the imported pre-existing auditor/pruner are immutable to the SNS runner,
owned by root under /usr/local/libexec/chadult-sns-retention.

## Scope and safety

- Fixed owned release root: /opt/github-runners/sns-growth-engine/.buffered-runtime/releases
- Preserves current and previous release symlinks, pending release if present,
  the newest independent bootable emergency release and the separately pinned
  historical recovery release bec16989c859e97abe53a736afb6d76bc12338a1.
- Every candidate must have a valid exact-SHA owner marker and have passed
  at least seven full days since release modification. Up to TWO releases can
  be reclaimed in one daily iteration.
- Before deletion, verify recent (36h or less) successful, centrally-owned
  AgentOps R2 backup AND R2 health service, plus enabled daily backup timer.
  This is in addition to previous SNS independent off-VPS R2 restore proofs.
- The pre-existing SNS release pruner takes the common VPS deployment lock
  and a tool-local cleanup lock. It rechecks all release pointers, open FDs,
  process working directories/command lines, expected device, mount points,
  SNS runner ownership, hardlinks, and exact SHA before deleting anything.
- The service has read/write permissions only under SNS release directory,
  the SNS-local lock and the shared deployment lock. It cannot write Docker
  assets, database volumes, other project releases, R2 or social accounts.
- The service reads other running processes only to reject in-use releases;
  it does not signal or modify other projects' processes.

The current-SHA release and fallback remain on the VPS. Source code is
reconstructible from its pinned GitHub revision; changing or restoring
application state is handled separately from this immutable build pruning.
R2 holds encrypted data/configuration snapshots; not all old virtualenv
binary copies are themselves uploaded to R2.

## Deployment and verification

Installation is approved only after local unit tests and static checks,
root-owned source sha256 verification, and a VPS no-delete audit pass.
The source is installed in the exact root-only path, and exactly two new
SNS-namespaced systemd units are added. Central AgentOps backup already
archives /etc/systemd/system; no new backup token, repository, cron, or VPS
snapshots are created.

Inspect:
  systemctl status sns-growth-release-retention.timer
  systemctl show sns-growth-release-retention.service -p Result -p ExecMainStatus
  journalctl -u sns-growth-release-retention.service --no-pager -n 20

A blocked cleanup must stay blocked. Never reduce the seven-day grace,
disable full-process scans, override a failed R2 backup guard, or change
shared R2 quotas just to reclaim storage sooner.
