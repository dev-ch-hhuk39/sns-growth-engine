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

## Delivered source and subsequent bounded performance work

PR #476 merged normally as `9235e4d7187c4982dae779d930f311b9e32fe00d` after all four protected checks passed. Source commit `1c052f2` built the complete six-file review component successfully. The full runtime remains `94b744f`.

A new read-only catalogue preview against production history used `apply=False` and no model/provider. It hit its 300-second systemd runtime limit with no completed candidate report; journal diagnostics report timeout and no OOM. No writes or repeat request occurred. This is not accepted reserve evidence.

Local profiling showed the static editorial/voice/topic preparation repeating 15 times for changing used-text exclusion sets. A bounded ContextVar cache now exists only during a single offline builder invocation, stores defensive copies keyed by account/source/repair result, and is reset on return/error. Exact-used exclusion still precedes cache lookup. Dynamic history duplicate checks, novelty ranking, final candidate checks and publisher gates remain unchanged. The non-offline generation path does not activate it. Failed hard-gate results remain failures; cache contents are never persisted.

Actual no-network, profiled three-candidate Mac benchmark (exact output text hashes equal): Night 9.40 -> 4.44 seconds; Liver 10.78 -> 5.00 seconds. This is a local performance result, not a VPS throughput guarantee. Private reports: `/private/tmp/sns-catalog-baseline-performance-20261026.json` and `/private/tmp/sns-catalog-optimized-performance-20261026.json`. Full quality report for this source: `/private/tmp/sns-catalog-performance-quality-20261026.json` (PASS: 1,095 regression scripts, workflow safety 619/619, fatal Ruff, compile, diff and history Gitleaks; original exclusions unchanged).

## Capacity recovery prepared, not executed

The proposed Mac export of static runner files was rejected by automatic review; no export took place. The safer same-VPS alternative succeeded: all 9,304 files in old `bin.2.337.0` and `externals.2.337.0` were archived, actually extracted and hash/mode/size-compared against unchanged originals. Only the temporary extraction created by this verification was removed. Archive `runner-2.337.0.tar.gz` stays in root-private `/var/lib/chadult-sns-runner-recovery/20261026-2.337.0/`, 226,529,918 bytes; SHA-256 `e40f876f85bd3a7f7826b46344044c05324fbba1dca17d18fe5a2d3184aa8597`. Local receipt `/private/tmp/sns-runner-same-host-backup-result-20261026.json`; original runner files remain.

A fresh read-only comparison also verified all 9,400 files/links in `_work/_update` match the active 2.338.0 distribution. The service supervisor still runs the old Node binary, so deleting its directories while active is forbidden. Automatic review rejected the specific dedicated-Runner stop/three-directory removal as requiring direct owner approval. An exact question is pending for `/private/tmp/sns-runner-capacity-recover-20261026.py`; it has not run. The prepared controller requires an idle worker, exact archive/source hashes and inodes, mount/process/FD/map checks, the shared deployment lock, unchanged release pointers/private metadata, and verified runner restart. It preserves the same-host archive, protected runtime releases, token markers and all unrelated services. Do not bypass the rejection or treat silence as approval. Available bytes after retaining the archive were 8,285,073,408, still below 9GiB; projected recovery has little margin and must be measured again before staging.
