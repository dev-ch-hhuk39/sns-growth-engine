# Phase 5B-4B + 5B-4C — Legacy media review migration safety

## Scope

This combined lightweight phase provides two development-only capabilities:

1. **5B-4B: staged strict mode for legacy READY approvals.** The legacy
   Sheets decision path (`publication_review_board.py` /
   `apply_publication_review_decisions.py`) and manual `approve_queue.py` CLI
   now support an explicit `--require-trusted-media-review` flag. Under this
   mode, a protected `night_scout` or `liver_manager` media candidate cannot
   be moved to READY merely because an editable Sheets cell says `OK` or
   an operator passed a `--reason` string.
2. **5B-4C: read-only legacy migration audit.** A sanitized standalone
   tool reports which protected media records are `WAITING_REVIEW`,
   already `READY`, or historically `POSTED`, with no changes to the queue.

## Default compatibility and security limitations

**Strict mode is opt-in for this phase.** Existing production workflow
behavior and existing default CLI calls remain unchanged. This is a safe
transition design, not proof that legacy approval bypasses have already
been eliminated. Do not enable strict mode in the shared VPS workflows until
the responsible operator approves its effect on media READY throughput and
the authoritative review service is available.

The target set includes the four managed media slots in Phase 5B-1.
For those two accounts, media markers (`media_required`, `media_type`,
`media_asset_id`, `media_url`, `generation_mode`, clip ID) also trigger
protection if `slot_id` is missing. Plain text and other accounts are
not changed. A queue row already READY remains a post-hoc feedback entry
rather than a new READY transition; **this does not establish publishing
safety for existing READY rows**.

In strict mode, `OK` on protected media returns
`BLOCKED_TRUSTED_MEDIA_REVIEW_REQUIRED` with no queue fields to update.
`NG` and `HOLD` retain their previous behavior. Neither mode initiates a
social post. Importantly, **no user-modifiable local review receipt may
override this block**: the trusted approval service remains unconnected.

Legacy auto-READY / other media-promotion scripts and live publishers have
not been secured merely by this change. All other write entrypoints and
publisher-side rights checks still require a separate inventory/security
review before authoritative approval is enabled.

## Read-only migration inventory

Use a **previously collected and authorized** Phase 5B-3 queue snapshot,
not a fresh VPS or Sheets operation in this development chat.

```bash
python3 scripts/audit_legacy_media_review.py \
  --queue-snapshot-json readonly-queue-snapshot.json \
  --output-json new-legacy-media-audit.json
```

The input must declare `sns_media_queue_snapshot_v1`, `read_only: true`,
a capture timestamp and no more than 200 records. Incomplete or malformed
inputs fail closed, and duplicates are rejected. The output is a **new**
0600-permission JSON file; it never overwrites prior results. It shows
sanitized queue/account/slot identifiers, status and review category only.
No post text, media links, transcripts, tokens or raw review notes are output.

The report labels existing READY rows
`EXISTING_READY_NEEDS_CANONICAL_RIGHTS_REVIEW`, which means review is
needed—not that their current rights are invalid. Similarly, the presence
of a prior `OK` cell is **not** authenticated-identity evidence.

## Validation and deployment boundaries

Test the legacy guard in both modes, explicit rejections/holds, media
identity omission, safe account scoping, duplicate snapshot handling,
no-leak output, no-overwrite file behavior and the protected manual CLI.

```bash
python3 scripts/test_legacy_media_review_safety.py
```

The full repository CI is mandatory before merging. This PR must not
modify current runtime settings, cron, VPS files, Sheets or production
queues. If a later rollout needs to change scheduled workflow arguments,
its concrete commit SHA, capacity/RAM gate, health/rollback and affected
media throughput must be handed to the dedicated shared-VPS management chat.

## Next heavy phase — Phase 5B-5

Connect the existing Phase 5B-4A policy to a **real server-side identity
provider, protected evidence repository and transactional authorization
ledger**. Atomic compare-and-swap must bind the current queue revision,
the latest review event and rights validity to the authenticated reviewer.
Add immediate prepublish rights/revocation revalidation; then audit and
retire all legacy approval bypasses before switching strict mode to
default. This requires choosing the authoritative datastore and
establishing secure operator credentials and rollback: not part of
the present source-only phase.
