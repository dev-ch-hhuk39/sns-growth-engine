# Review recovery and free reserve generation — 2026-10-26

This checkpoint uses actual host/CLI receipts. Source tests do not grant production acceptance. Base main is `203364e` (PR #475); full live release remains `94b744f`.

## Approved production review recovery

The owner explicitly approved the bounded repair: append seven missing review rows, update eight projection cells across two rows, independently verify readback, preserve quarantine evidence, switch to audited source and restart the existing review timer only after success. No queue, manual decision, note, token or SNS publication was authorized by that repair.

The repair made exactly one append request and one cell-update request. The supervising transport initially disagreed with the completed child result; no request was resent. The durable verified receipt and an independent read-only audit established the successful result. Source/plan changes would have blocked reuse.

The first standalone worker exposed a packaging omission: `apply_publication_review_decisions.py` needs `config/autonomous_mode.json` under its own root. It stopped before Sheets client construction and left its intent for reconciliation; the timer stayed disabled. A new immutable complete bundle included the exact policy already deployed (media still disabled). Real sync/apply CLI read-only invocations passed before conditional restart. Both the original and packaging-failure markers were archived with their hashes, not erased or silently retried.

Final host result: `RESTORED_VERIFIED`, reviewable 1,652, review rows 1,659, queue rows 2,070, missing projections 0, projection drift 0, unverified feedback 0, pending explicit decisions 0, verified feedback 10. First actual worker: PASS, 1,652 unchanged, 0 appended, 0 updated, 0 decisions, read-after-write true, 0 posts/paid AI. Existing review timer is enabled and active; independent consistency monitoring remains active.

Installed component: `/usr/local/libexec/chadult-sns-review/3a9e0891b09d6476d1cab08451829aa644c0e5dd-complete/`. It uses the unchanged live Python and libraries, immutable root-owned sources and the existing sandbox/locks. It is not a full-release switch. Active service drop-in: `40-complete-review-source.conf`; earlier files remain preserved.

Private evidence:

- `/private/tmp/sns-review-repair-verified-source-evidence-20261026/apply.json`
- `/private/tmp/sns-review-repair-outcome-readonly-result-20261026.json`
- `/private/tmp/sns-review-complete-cli-readonly-result-20261026.json`
- `/private/tmp/sns-review-restoration-complete-result-20261026.json`

## Source fixes derived from that recovery

`sns_review_component_bundle.py` builds only the six fixed runtime files from one full Git commit, including the autonomous policy and permanent thin launcher. It does not install or execute the bundle. Missing/extra files, unpinned revisions, media-enabled policy or pre-existing destinations block the build. Sources are hashed, fsynced and read-only. Actual packaged CLI tests use an in-memory Sheets boundary, verify the worker's output contract and detect missing configuration before client construction. This prevents substituting helper-level tests for packaged entrypoint evidence.

## Explicit free reserve route

`maintain_text_ready_inventory.py --bank-offline-only` is an opt-in, single-account confirmed Bank apply mode. It restricts generation to the existing offline original-text catalogue. It cannot be combined with reuse modes. Existing strict approval, global-history duplicate checks, canonical slot allocation, publisher validation, mixed-batch rejection and literal readback remain mandatory. Exhausting the finite catalogue stops this route without falling through to a paid model or reporting the shortfall as success. No production invocation or Bank write has been made for this new option.

Local Ollama generation also supports the two already-installed local model tags and a 1–25-call batch budget. The fixed localhost HTTP sink rejects redirects and bypasses environment proxies. Model choice is recorded on pending drafts; qualified larger-model output goes to its own private folder. No cloud model is accepted and no new model was downloaded.

Actual larger-model trial: three calls/account, Night 0 accepted / 9 rejected, Liver 1 accepted / 6 rejected. These are local quality passes only: global-history, slot, factual/editorial approval and publisher acceptance are outstanding. Original 48 pending drafts remain byte-identical. Receipt: `/private/tmp/sns-large-local-draft-trial-result-20261026.json`. The 14:32 live Bank audit (Night 12/30, Liver 11/30, Beauty 36 distinct / 30 slot-effective) predates later queue additions and must not be presented as a fresh current count.

## Independent blockers and additional verification

After PR #475's real CLI integration fix, [the protected-main App-ID verification run](https://github.com/dev-ch-hhuk39/sns-growth-engine/actions/runs/40294188525) returned `APP_PIN_PREFLIGHT_BLOCKED_META_APP_ID_MISMATCH`. The configured GitHub Liver App ID fails comparison against the live token's app. No ID pin was saved and no real refresh was attempted. A correct independent Threads App ID is needed; deriving the expected app from the token under test or guessing another account's ID would defeat the check. Night's unknown-outcome marker remains intact; Beauty is not part of this bridge.

Actual isolated P0 snapshot/restore: `RESTORE_REHEARSAL_PASS_NO_CUTOVER`, snapshot and restored copies match and signature checks pass. Production source and settings were unchanged; posting and cutover remain unauthorized/OFF. The source ledger contained zero claims and zero send attempts. This verifies an empty-ledger local restore, not a populated production history or fresh R2 restore. Receipt: `/private/tmp/sns-p0-live-readonly-restore-drill-result-20261026.json`.

Latest dedicated-runner metadata: 8,513,716,224 available bytes versus the unchanged 9GiB floor. Old runner binaries/externals plus downloaded update staging occupy about 1.4GB; a live process still references an old directory, so none were removed. Every retained runtime venv depends on Python 3.11.17 in the live toolcache. All eight runtime releases remain protected by retention/rollback. Receipts: `/private/tmp/sns-runner-owned-root-capacity-audit-result-20261026.json` and `/private/tmp/sns-runner-cleanup-reference-result-20261026.json`. Full release/security patch, all 13 hosted operational schedule replacements, accepted reserves, signed real canaries and timed metrics remain incomplete.

## Validation

Focused package, reserve, generation and network-inventory tests pass. The first final full run found one stale source assertion after proxy blocking was added; it was updated to require both proxy and redirect blocking, with behavioral transport tests. Corrected full result: `/private/tmp/sns-free-refill-quality-corrected-20261026.json` (PASS: 1,095 scripts, zero failures; workflow safety 619/619, fatal Ruff, compile, diff and history Gitleaks PASS). Protected PR checks remain required. No test exclusions, permission thresholds or publish gates were weakened. `docs/goal-status.json` is unchanged.
