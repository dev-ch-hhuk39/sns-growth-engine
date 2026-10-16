# P0 Threads text one-use authority: private host initialization

Status: CODE READY, NOT DEPLOYED. Night Scout / Liver Manager text only.
No protected media, Beauty, X, Google Sheets authority migration or production
posting is permitted by this preparation.

## Live evidence as of 2026-10-16 JST

The existing sns-growth-xserver runner is online. Manual read-only
GitHub Actions audit via protected main (run 38856286902) found:
- .buffered-runtime/current release, Python venv, launcher, and cron installed.
- 0600 private runtime.env readable by the authorized runner.
- BUFFERED_POSTING_ENABLED is not true (posting remains OFF).
- No SNS_P0_ONCE_GATE_ENABLED, DB path, or local HMAC key in runtime.env.
- The running release is not yet the completion branch.
- Existing operational Sheets contain historical ambiguous/failure statuses,
  and external writer exclusivity is not proven. No production cutover.

## One-time initialization (separate from cutover and authorization)

Workflow: provision-p0-once-host-authority.yml on PROTECTED MAIN ONLY.
It must NOT be dispatched from a PR or an untrusted ref.

Requires intentional, separately authorized operator decision and:
1. Stored read-only Sheets audit and independent immutable backup, and
   assurance that runtime.env indicates BUFFERED_POSTING_ENABLED=false.
2. Owner-only runtime/shared directory (0700), runtime.env (0600), and
   the preexisting shared global deployment lock.
3. No existing p0_once_private directory, P0 DB or signing-key settings.
   A partial run must fail closed and be manually reconciled; NEVER
   delete/recreate an in-use ledger to overcome a deployment error.
4. Manual confirmation string INITIALIZE_PRIVATE_P0_NO_POST.

Execution writes ONLY:
- shared/p0_once_private/once.sqlite3 (private local SQLite; new/exclusive).
- shared/p0_once_private/initial_backup.sqlite3 (private verified backup).
- runtime.env updated atomically to carry a locally generated 32-byte HMAC
  key and private DB path. SNS_P0_ONCE_GATE_ENABLED is explicitly FALSE.

Output is fixed, redacted JSON (no DB path, HMAC key, content or tokens).
Never copy HMAC key to Actions secrets, git, artifact or external dashboards.
Initialization is NOT permission to enable posting. It does not import historical
queue IDs, attest Sheets snapshots, stop legacy writes or provide a cutover.

## Recovery / audit principles

- The initial empty DB backup is proof of successful provisioning only. **Never
  restore this empty backup after ANY real CLAIM/HTTP attempt.** Doing so
  destroys anti-replay history and can cause duplicate provider posts.
- Later backups must preserve the full latest SQLite journal, HMAC and any
  uncertain POSTED_SAVE_FAILED attempt. A missing/mismatched HMAC or lost
  journal means STOP and supervised provider reconciliation, not auto retry.
- Final enablement requires operator proof that all old publisher and Sheets
  writer paths are stopped, immutable live Sheets snapshot/readback and
  queue/post reconciliation, a fresh private DB backup and test restore,
  correct profile token/handle checks and a bounded non-media Night/Liver
  canary. The new worker must enforce this at the HTTP sink.
- Do not classify code checks or the existence of runtime env keys as
  evidence of successful provider posting, media rights or PDCA performance.

## Tests

scripts/test_provision_p0_once_host_authority.py covers nine no-network
bootstraps: private owner and permissions; backups, HMAC and SQL verification;
strict no-post flags; double-init rejection; partial state; wrong confirmation;
symlinks, duplicate/shell-shaped env and busy deployment lock.
scripts/test_p0_once_runtime_preflight.py verifies ledger state and tamper
detection without granting runtime publish authority.
