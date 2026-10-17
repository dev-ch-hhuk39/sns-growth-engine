# Legacy Threads orphan recovery — live provider proof required

## Problem that was fixed

The historical `recover_orphan_threads_post.py` could previously mark a queue
`POSTED` and create a `real_post=true` recovered result merely from a
user-supplied `--external-post-id`, or with an empty identity via
`--skip-api-lookup --apply`. A first-20-character text prefix could also be
accepted as a Threads match. These are **not sufficient proofs** of an actual
post, and could fabricate successful delivery history.

## New apply contract

An existing result can be manually recovered only if all checks pass:

1. The queue belongs to the selected Night Scout or Liver Manager account and
   has a genuine unresolved publish-save state:
   `POSTED_SAVE_FAILED`, `POSTED_SAVE_UNVERIFIED`, or
   `PUBLISH_OUTCOME_UNVERIFIED`.
2. Live read-only Threads API access through that account's own credentials
   returns **exactly one** matching full text. Prefix matching is forbidden.
3. The provider's post ID is numeric; its actual permalink is HTTPS and on
   `threads.net` or `threads.com` with a post path.
4. The provider timestamp is within 15 minutes of the recorded queue
   `processed_at`, and both timestamps contain time zone offsets.
5. Optional `--external-post-id` and `--post-url` can only serve as exact
   expected-value filters; they **never** replace the live provider lookup.
   `--skip-api-lookup` always blocks apply.
6. The post-result append is attempted **once**, without retry after an
   ambiguous Google Sheets response. The newly written result is read back
   exactly once before changing the queue.
7. The queue update must succeed and be independently read back, otherwise
   the process returns `PARTIAL_SAVE_UNVERIFIED_NO_RETRY` and stops without
   generating follow-on logs/PDCA rows.
8. Metrics remain `MANUAL_PENDING`; this is **not** proof of 24h/72h/168h
   measured results, and the recovered row is not automatically an accepted
   activation canary.

## Operator examples (do not run unattended)

```bash
# Read-only discovery: unique provider text+ID+URL+timestamp verification.
python3 scripts/recover_orphan_threads_post.py \
  --account-id night_scout --queue-id APPROVED_EXACT_QUEUE_ID

# Apply is for a specifically approved existing uncertain-save row only;
# it REQUIRES live provider proof and never performs another Threads POST.
python3 scripts/recover_orphan_threads_post.py \
  --account-id night_scout --queue-id APPROVED_EXACT_QUEUE_ID \
  --external-post-id EXPECTED_NUMERIC_ID --apply
```

Before applying, verify that this manual legacy Sheets writer is the sole
authorized repair writer and that a recoverable production snapshot exists.
The tool does **not** provide a cross-host atomic Sheets compare-and-swap, and
cannot replace the P0 one-use publisher journal. Never automatically rerun
after a partially acknowledged Sheets write.

Older cases beyond the last provider API page, lacking queue timestamps or
without an exact provider URL must remain for independent human/provider
reconciliation rather than being marked posted. No SNS post or Sheets apply
was executed in these development changes.

## Tests

```bash
python3 -B scripts/test_recover_orphan_threads_post.py
python3 -B scripts/test_orphan_provider_proof_required.py
```

The adversarial suite covers false text prefixes, duplicate exact matches,
invalid URLs/IDs, wrong account/queue state, missing or inconsistent timestamp,
skipped API, conflicting supplied IDs, redacted exceptions, ambiguous append,
and mandatory queue/post result readback. No network or production data.
