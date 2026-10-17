# SNS Growth Engine | 2026-10-17 staged no-post deployment incident

## Confirmed facts

- GitHub run 39024199547 staged revision bec16989c859e97abe53a736afb6d76bc12338a1 with posting_enabled=false.
- Shared VPS preflight passed before staging. Installing the release used approximately 730 MiB. A later strict 8-GiB preflight was denied after the current symlink had briefly been promoted.
- EXIT rollback reset current to f6b78bacd6fa4a72d67894bd3c09cbac38391d99, and env remained owner-only 0600 with BUFFERED_POSTING_ENABLED=false, SNS_P0_ONCE_GATE_ENABLED=false, SNS_P0_AUTONOMY_MODE=canary.
- Cron still showed 2 SNS markers after failure, but direct cron rollback had logged an error opening its backup filename. This prevented the release from being considered healthy/finished.
- Old current and previous pointers were preserved. Failed candidate bec16989... still exists as an immutable release, and pending points at it. Do not destroy that directory or clear pointers casually.

## Code remediation

1. Require 9 GiB at workflow/start-of-transaction before staging a new immutable release. Existing 8 GiB guard is rechecked after staging and **before promotion**, not solely after a potentially destructive pointer swap.
2. Snapshot the SNS cron strictly; retain its original bytes on an open file descriptor. Restore cron only if scheduler mutation began. This avoids restoring an unchanged cron from a possibly removed path.
3. Track pending pointer created by a transaction. On failure, remove only the exact symlink created by that transaction under the shared lock; retain staged release files for forensics.
4. Provide a separate main-only, approval-gated tool/workflow for legacy abandoned pending links. It requires exact current and pending SHAs, owner-only posting OFF runtime state, current/previous protection and the global deployment lock. It unlinks only pending; it NEVER deletes the staged release.
5. Offline negative tests cover symlink escape, wrong hashes, posting ON, lock absent, and rollback release protection. They do not publish, modify Sheets, or access any VPS.

## Operational next actions and stop conditions

- First inspect then resolve the exact abandoned pending link (bec16989...), only if current is still f6b78bac... and posting/P0 remain OFF.
- Do not try another deployment until shared VPS headroom meets 9 GiB at the start. This may require safely aged (>=7 days), explicitly identified SNS-only release cleanup or independent VPS capacity expansion. Other projects and files remain prohibited targets.
- After an eventual posting-OFF deploy: independently inspect installed SHA, env ACL and OFF switches, scheduler and ledger; require read-only restore and no-post Sheets plan; stop immediately if any part differs.
- Night Scout provider handle is still missing and external old writers/historical uncertain sends have not been attested. No real post or continuous launch authorized.

A passing security scan and patched rollback path do not prove that every future filesystem, scheduler or provider error is impossible.
