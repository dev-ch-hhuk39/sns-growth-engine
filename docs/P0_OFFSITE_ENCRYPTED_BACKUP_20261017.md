# SNS Growth Engine | P0 off-VPS encrypted snapshot and restore

2026-10-17 JST. Scope: Night Scout/Liver Manager Threads text one-use ledger only.
This mechanism does not enable posting, change Sheets, attest legacy-writer
disablement, or authorize an automatic restore.

## Purpose and custody

- The source P0 ledger is a private 0600 SQLite file under the SNS-only
  VPS buffered runtime. Existing signatures depend on its long-lived HMAC
  secret. The two must be preserved consistently.
- The exporter acquires the shared production deploy lock, refuses unless
  both posting and P0 gate are OFF and continuous mode is NOT active, takes
  a consistent SQLite backup, runs PRAGMA integrity_check, includes only
  necessary P0 HMAC key + signed approvals (if present), and encrypts the
  bundle with the operator's age public recipient *before* writing stdout.
- It never writes an unencrypted backup outside a protected temporary
  directory. Its only stdout is encrypted age data; keys and raw post text
  must not be logged, committed, sent by email, or stored in Actions.
- For the first snapshot, the Mac operator's SSH user had sudo access to
  just the SNS runtime; no runtime directory permission was changed.
- On the operator's Mac, snapshots and the age identity reside in an
  SNS-project-specific 0700 directory. Files are 0600. No other project
  folder is in scope. An independent offline copy of the age identity
  and periodic retention checks remain separate operator obligations.

## Operator Mac invocation (manual only, never as a scheduled publisher)

These commands are examples; use the verified Mac SSH alias, checked runtime
revision, owner-only path, and current expected SHA. Never copy a secret value
to terminal output. Never let a CI job capture unencrypted Python stdout.

1. Prepare a dedicated local 0700 folder and age recipient. Store the
   PRIVATE age identity solely in an operator-controlled location with
   0600 permissions; it must not go to GitHub.
2. Obtain the age1... public recipient without displaying the private key.
3. After proving posting OFF and P0 gate OFF, from the Mac run:

       ssh -T -o BatchMode=yes fukuri-vps-admin          "sudo -n python3 - --recipient PUBLIC_AGE_RECIPIENT"          < scripts/export_p0_encrypted_offsite_snapshot.py          > /operator/private/p0-snapshot-new.age.partial

   Rename the ciphertext atomically only if the SSH command exits zero.
   The output has an age header and is NOT plaintext or a live restoration.
4. Test decrypt + independently restore signed ledger into disposable
   operator-only storage:

       python3 -B scripts/verify_p0_encrypted_offsite_snapshot.py          --encrypted-file /operator/private/p0-snapshot.age          --identity-file /operator/private/age-identity.txt          --expected-release-sha ACTUAL_CURRENT_SHA

   Expected: RESTORED_AND_HMAC_VERIFIED_NO_CUTOVER. The private signing
   key and provider tokens never appear in the report.

## Critical restoration rule

NEVER overwrite the production ledger with an older snapshot automatically.
If an irreversible CLAIM or SEND has happened since capture, restoring an old
empty or stale ledger could permit a duplicate post. Manually reconcile
provider results and queue records, preserve the newer ledger, and obtain a
fresh owner-approved recovery plan before any cutover.

An off-VPS encrypted snapshot plus disposable verified restore proves an
additional disaster recovery capability. It does **not** prove:
- a second independent copy of the decryption identity,
- all external writer credentials revoked,
- historical posted/SEND outcomes reconciled,
- recipient account identity checked at the provider,
- current queue/slot/text approved and P0 host approval signed,
- the live 24h/72h/168h metric results,
- permission for a real post or for continuous autopost.

The operational GO/NO-GO remains in
docs/P0_EXACT_SIGNED_CANARY_RELEASE_20261017.md and
docs/P0_CONTINUOUS_POST_RELEASE_20261017.md.
