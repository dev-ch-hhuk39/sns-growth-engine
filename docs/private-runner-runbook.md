# Private Runner Runbook

This repository is intentionally private. Do not convert it to public while
`PUBLICATION_AUTHORIZED=false`.

## Production runner

GitHub-hosted Actions are currently rejected before job startup by the account
Actions/billing limit. Register one always-on private runner with the labels
`self-hosted` and `sns-growth` on a VPS or a dedicated Mac. Store its runner
registration token outside this repository. The runner service must run as a
non-admin account with a private working directory and no browser profile.

Before moving a scheduled workflow to this runner, run its dry-run mode and
verify that the Sheets health row reports no missing schema or credentials.
Only then change that workflow's `runs-on` to `[self-hosted, sns-growth]`.

## Safe first production sequence

1. Run `seed_owner_attested_media_permissions.py --dry-run`.
2. Apply the ledger only after the owner attestation has been reviewed.
3. Run source discovery with `--dry-run`; this makes no network call.
4. Use one explicitly selected source post for an ingest dry-run.
5. Confirm one text slot reaches a new Threads URL and is saved in
   `posted_results` and `content_slot_runs`.
6. Confirm one direct image/video slot only after its permission ledger row,
   asset hash, Cloudinary URL, and media validator are present.

Never enable X or beauty, never put credentials in logs, and leave a mixed
carousel to text fallback until an official multi-item Threads implementation
has been verified.
