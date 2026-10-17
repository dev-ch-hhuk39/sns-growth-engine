# Legacy GitHub direct SNS posting quarantine (2026-10-17 JST)

Production's sole intended text publisher is the one-use ledger guarded VPS launcher. The guarded runtime is currently OFF: **do not enable it as part of this change**.

## Identified fail-open cross-host risk

The repository's old GitHub-hosted account jobs could conditionally publish if their activation settings or BUFFERED_INVENTORY_ACTIVE variable were not in agreement with the VPS. Current source-level switches in config/production_inventory.json and config/autonomous_mode.json are active, while the VPS posting authority is disabled. A green VPS audit does not prove an older Ubuntu Actions job will never attempt direct publishing.

## Source-level quarantine applied

- All direct-real-post steps in the two account autonomous loops, manual autonomous loop, Beauty scheduled/manual text and media, two direct-reference-media loops, two media-growth-post loops, and TikTok Shop onboarding now have a literal always-false step condition. Source of each post step is retained for audit; no post step may run on any GitHub event.
- The manually dispatched Threads queue worker rejects real_post and direct owner approval before any potentially mutating Sheets repair/approval action, retaining dry-run behavior.
- Self-hosted content-slot-recovery retains its VPS launcher path; if buffered activation is absent, the old legacy direct backfill is no longer called. Recovery remains governed by the host private posting switches and one-use gate, which are OFF.
- This does not disable independent acquisition, reference analysis, review, metrics, or safe content preparation stages. It deliberately does not enable actual publishing, including Beauty or media.

## Guarantees and limits

Literal always-false guards resist changes to runtime/GitHub variables; source changes require a protected-main PR with tests. The static adversarial regression audits every active workflow step advertising real-post permissions and refuses reintroduced direct senders.

This is not proof that all external apps, other hosts or historic publishers are disconnected, and it does not repair ambiguous previous provider outcomes or Sheets data. Any external manual tool not backed by this GitHub checkout remains outside the guarantee. Do not enable VPS P0 or schedule posting until unique-authority, provider-result reconciliation, backup/restore, account ownership/rights and exact content approval are verified.
