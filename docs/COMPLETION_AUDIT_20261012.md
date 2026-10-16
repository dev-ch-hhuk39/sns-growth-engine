# SNS Growth Engine completion audit — 2026-10-12

## Scope and evidence

Base: `57ef785118ca9c34679723d94151435ce2f30dca`, PR #393. The GitHub connector confirmed that remote main matched the dedicated worktree at audit time. Branch: `codex/sns-growth-engine-completion-20261012`. Initial tree clean; no other worktree was changed.

This is a source and offline-test audit, not a fresh production assessment. The baseline repository suite passed **973/973** scripts; the baseline metrics subset passed **24/24**. External credential/network probes and optional local-tool probes remain excluded by the existing runner. Historical production statements in handoffs have not been recertified.

## Four-way classification

| Classification | Capability and concrete evidence | Remaining work |
| --- | --- | --- |
| Implemented and locally tested | Reference discovery/normalization, rights and lineage validation, generation/review: existing pipelines and `media_post_validator.py`; publisher-level physical-media stop in `src/publishers/media_publish_interlock.py` | Real source/provider/quality evidence and approved media rollout |
| Implemented and locally tested | Text replenishment, bounded regeneration/fallback, delayed-slot recovery: `run_scheduled_text_slot_pipeline.py`, `run_slot_text_fallback.py`; account-scoped preparation/dispatch tests | Natural scheduled evidence on the intended runtime; not a new scheduler implementation |
| Implemented and locally tested | Result identity/readback and no-repost recovery: `process_threads_queue.py`, `publisher_delivery_contract.py`, `recover_orphan_threads_post.py` | Production reconciliation of any actual unknown outcomes |
| Implemented and locally tested | Metrics snapshots, partial-measurement preservation, bounded attempts and snapshot resume: `process_threads_metric_jobs.py`; measured-only PDCA in `metrics_pdca_contract.py`, `run_pdca_cycle.py`, attribution and generation consumers | 24/72/168-hour observations and later same-account consumption |
| Code exists, integration incomplete | 6E–6P protected SQLite snapshots, managed commands, outbox, one-row reporting writer, ACL and dual-operator/IdP verification | Actual trusted identity enrollment, protected runtime binding and legacy operational writer cutover; reporting mirror does not replace operational queue |
| Not implemented at baseline; implemented here | `schedule_threads_metric_collection.py --apply` was an unconditional stub; post-success reservation writes returned added count without readback | One-result gated repair, read-only planning from live Sheets, verified total reservations and account-safe collection now have offline tests; live execution pending |
| Not implemented | Real IdP login/MFA issuance, trusted session provisioning/revocation callback and operator-facing approval issuance; authenticated production media publishing authority | Select the actual IdP and prove its MFA/session semantics before implementing provider-specific production integration |
| External permissions/environment/human approval required | Real reporting-only Google identity/ACL evidence, migrations 0010–0013, real two-person canary, shared-VPS deployment and runtime cutover | Owned by the separate VPS operations chat; no migrations, writes, login, media acquisition/upload or posts performed here |

## Scope conflicts are explicit

- `AGENTS.md` limits current work to Night/Liver and excludes Beauty operations. `GOAL.md`, `config/goal_acceptance.json`, `production_capability_matrix.json`, `autonomous_mode.json` and `media_growth_engine.json` include Beauty; text config currently has activation flags enabled. These settings are **not fresh owner permission to operate production**. This change preserves them and limits the new manual repair writer to Night/Liver. Existing common publisher behavior is not reconfigured.
- GOAL allows explicitly recorded degraded text fallback in media slots, while additive legacy acceptance still includes `media_slots_no_text_fallback`. Do not remove old criteria or claim all acceptance complete to conceal this mismatch.
- Acceptance retains hosted-only/no-VPS historical criteria while deployment/runtime code includes the VPS publisher boundary. The owner explicitly assigns VPS changes to a different chat. This development task does not resolve that governance discrepancy by deployment.
- Media config has enabled flags, but the current publisher interlock intentionally refuses physical-media network delivery. Config booleans alone cannot override it.
- Repository configuration examined does not identify a usable operator IdP integration. No vendor or production token was invented. `docs/goal-status.json` is unchanged.

## Implemented reservation lifecycle

`verified POSTED result -> exact 24/72/168 reservation plan -> at most one RAW append of missing jobs -> uncached readback -> three verified reservation identities`

New shared `metrics_reservations.py` is used by the existing post-success worker and the existing scheduling CLI. Only `metrics_collection_jobs` is written. No new database, migration, queue, identity service or automatic workflow is introduced.

- Match result/account/platform/post URL/window/due time and deterministic job IDs. Missing or ambiguous results, unverified external identity, duplicate jobs, foreign-account collisions and cancelled/conflicting reservations block writes.
- Preserve COMPLETE/COMPLETE_PARTIAL/FAILED reservation rows and attempt counts. A verified reservation count is not successful metric measurement.
- Return the total confirmed reservation count, including existing rows, instead of only this invocation's additions.
- Batch at most three missing rows with RAW values; never apply generic append retry logic. A lost response may be reconciled by readback only; absent/partial/unreadable readback fails with `metric_reservation_outcome_unknown_manual_reconciliation`.
- The consumer now cancels account-mismatched or ambiguous-result jobs before an Insights API target can be built. It no longer combines another account's post with the job account's credentials.
- The Sheets mutation manifest intentionally adds **one** reviewed `append_rows` callsite. The existing inventory assertions are unchanged.

**Limit:** Google Sheets append has no transactional CAS with the source read, no uniqueness constraint and no distributed lock. This repair command must be run with reservation writers serialized and no concurrent editing. Unknown outcomes require operator inspection; the command has no durable cross-invocation uncertainty journal and must not be put in an automatic retry loop. It does not promise exactly-once writes across processes or activate an aftercare repair schedule.

## Date-dependent text fallback correction

The second full run exposed a preexisting Liver first-viewer template failure: date-based selection could produce a body without explicit reasoning or enough account context. The body now explains why a two-choice question helps first-time viewers comment. All nine hook/closing combinations pass the unchanged public-text/persona validator; no scores, thresholds or test expectations were relaxed.

## Critical path

1. Merge the tested reservation/collection correction after remote CI succeeds. This closes a concrete break between verified posting and measured feedback without another authentication phase.
2. Operations verifies deployed revision, actual text supply, result persistence, reservation integrity and natural aftercare runs for Night/Liver. Use live evidence only for production acceptance.
3. Owner resolves Beauty/legacy-acceptance scope and identifies the real IdP. Operations provisions approved staff identity, reporting principal and restricted destination; run read-only ACL checks before any approved one-row write.
4. Finish legacy writer cutover by source, with backup/restore and a single operational authority. Keep media publication blocked until separately accepted publish-time rights/identity/outcome integration is implemented and proven.
5. Collect real scheduled runs, timed observations and measured PDCA feedback. Pending wall-clock evidence is observation work, not something mocks can close.

## Operations handoff (instructions only, not executed)

Prerequisites: approved deployment, existing metrics sheet with full schema, a verified POSTED result, no concurrent reservation writer/editor, normal credential handling by operations. This PR needs **no DB migration**. Read-only inspection:

```sh
python3 scripts/schedule_threads_metric_collection.py \
  --use-sheets --dry-run --account-id night_scout --result-id RESULT_ID
```

Only after separate production-write approval, use one exact reviewed result:

```sh
ALLOW_METRICS_SCHEDULE_WRITE=true python3 scripts/schedule_threads_metric_collection.py \
  --use-sheets --apply --confirm-metrics-schedule \
  --account-id night_scout --result-id RESULT_ID
```

Do not use offline JSON to authorize a live repair; the CLI rejects this. Repeat the read-only command to verify three matching reservations and no remaining jobs. Check unchanged queue/result identities and unchanged existing metrics. Existing aftercare collects due reservations; this command never collects or fabricates measurements itself.

On any unknown/partial outcome, stop writers and inspect the exact three job IDs with an independent read. Do not retry the apply command automatically, reset jobs, delete rows or repost. Escalate duplicates/conflicts for reviewed data reconciliation. Rollback is to stop use of this repair command and deploy the previous approved code through operations; preserve all reservation/snapshot records. No automatic data rollback or production deletion is provided.

## Validation and delivery

- Focused new lifecycle/CLI/account-isolation tests: 18 cases PASS.
- Existing IdP/operator integration suite: 241 cases PASS; existing result-repair, metric batch-resume and network/Sheets inventory tests also run.
- Workflow safety: 527 PASS, 0 FAIL across 49 workflows.
- Post-change regression run 1: 973/974 (old publisher marker). Run 2 exposed a preexisting date-dependent fallback failure; both root causes fixed and focused reruns passed. **Final full repository run: 975/975 PASS**, zero failures (8 external probes and 3 optional-tool probes excluded). Ruff fatal rules, compileall and diff checks PASS.
- GitHub CLI access restored on continuation after the earlier credit-related approval failure. Remote main remains `57ef785`; Local verification complete; PR/CI/merge pending.
