## 2026-09-10 Live Preparation Follow-up

- Saved clip caption evidence preserves numeric `start_seconds=0` instead of rejecting it as missing; negative, non-finite and reversed ranges remain blocked. This fixes a real saved-asset selection blocker without changing rights or persona gates.
- PR #294 merged normally as `79052a55981702850755ab445f750afa501b84af`. Exact HEAD `ddbb3e5417133a5134bc980b84344f66502432e3` passed PR CI `34418003085` and full CI `34418086153` (tests, dependency audit, secret history).
- Production preparation started from that main; this is not proof of successful delivery or complete inventory. Beauty bank admission reached 23 usable candidates, but its account-scoped Hybrid ledger reached the unchanged daily limit of 40.
- Follow-up preserves BOTH whole-Sheets verification steps. AUTO_READY preparation matrix uses `max-parallel: 1` to reduce shared Sheets 429 pressure; failures remain isolated (`fail-fast: false`). Bank writes require a successful credential/activation/kill-switch guard even after other steps fail.
- Explicit redacted execution/daily/monthly budget reasons are persisted. Once approval capacity is exhausted, preparation stops further generation in that account invocation and may allocate only already-validated canonical evergreen reserves. No budget increase, synthetic approval or quality relaxation.
- Buffered activation remains false. No new Threads post has been performed for this rollout. Real media inventory, horizon coverage and reconciler evidence still require validation.

## 2026-09-10 Buffered Production Inventory

Current branch: `feat/buffered-production-inventory`; base main: `aff033999ec8261470c893168590c02a3b58fdb0`.
Status: implementation and local regression verified; production cutover NOT yet verified.

- Current Owner scope is Night Scout, Liver Manager and Beauty, including autonomous low-risk approval. Older two-account / Beauty-human-review-only notes below are historical, not current operating policy.
- Preparation builds 72-hour canonical text primary/reserves (3 per slot), plus a target of 30 unused strictly validated evergreen candidates per account. Bank admission uses bounded batch writes with read-after-write; no approval cloning or POSTED queue recycling.
- Direct and clip preparation refill separate validated media buffers (minimum 3). Saved rights-valid Cloudinary assets are preferred; acquisition and generation never execute in the buffered publisher.
- The existing Content Slot Recovery workflow scans every five minutes, accounts independently, with the same per-account publishing lock. It consumes at most one exact due queue per account/run, within a 240-minute window and existing caps/cooldown. Uncertain publish outcomes stop retries.
- Owner-authorized media shortage may use a validated text reserve. Evidence retains expected media and actual `text_fallback`; this is never counted as media success.
- Beauty retains two daily slots; the 20:30 slot alternates direct media and approved clip after cutover. No extra daily posts are added. X publishing stays disabled.
- Cutover requires `config/production_inventory.json` activation plus `BUFFERED_INVENTORY_ACTIVE=true`. Until inventory is verified, activation remains false and legacy production workers are retained. Do not set the variable first and disable working publishers prematurely.
- Local regression: 901 script tests PASS; focused inventory/reconciler/generation/clip-preparation tests, Ruff, compileall and CI Mypy PASS. These are not production evidence.
- Latest read-only Sheets acceptance: text coverage 0%; usable evergreen Night 21 / Liver 25 / Beauty 0; validated media reserve 0 for all six account/route pairs. Legacy posted-results evidence includes 2 duplicate records and 64 unverified/missing-metrics records. No cleanup or replay is authorized by those counts alone.
- Remaining: exact-head CI and normal merge, real inventory refill/readback, staged activation, real reconciler delivery/repeat-run proof, metrics and PDCA verification. Completion must remain false until these pass. Do not wait for future 168-hour metrics merely to close code development.
- Preserve `.runtime/` unchanged and uncommitted. `.ai-tmp/`, credentials and runtime outputs are excluded from Git.

## 2026-09-07 Follow-up: Stale Approval and Delayed Slot Recovery

- Automatic READY approvals with stale Hybrid evidence are explicitly withdrawn to WAITING_REVIEW and read back before bounded re-evaluation. Human-approved, excluded, cross-account and POSTED rows are never refreshed this way.
- Autonomous preparation requests this refresh; publisher validation remains mandatory.
- A late text schedule event may recover only its exact overdue slot from prebuilt inventory, using existing activation, lease and publisher gates. Missing inventory or an unrecoverable slot is a failure, not a successful no-post.
- Local focused refresh/recovery tests PASS. Production completion remains unverified; provider capacity and media suitability failures remain tracked separately.

## 2026-09-07 Scheduled Inventory Delivery Repair

Status: implementation verified locally; production completion NOT proven.
Base: bfea7cb899dc171aeefa80735d5d066567f0984d.

- Scheduled text and missed-slot recovery now consume the exact account/slot/date READY inventory before spending another generation call.
- Unused READY direct media can carry forward from an earlier preparation date; future/expired candidates remain excluded. Publisher rights, provenance, duplicate and account checks remain mandatory.
- Autonomous low-risk approval is explicit for newly generated scheduled text. Failed preparation retains a redacted provider failure category; stale review output cannot approve a new candidate.
- Ambiguous publish outcomes never trigger another candidate. Activation, slot lease and persistence checks remain unchanged.
- Local focused test scripts: 10/10 PASS, including prepared inventory unit cases. No production post is evidence for this patch yet.
- Still to verify: delayed GitHub schedule delivery, provider quota exhaustion, direct/clip eligible inventory, and real post/read-after-write/metrics results. Earlier completion claims and historical two-account/Beauty-review-only notes below are not current production evidence.

# START HERE - V1 Production Completion

Updated: 2026-08-28

## Read first

1. Current user task and task-specific Owner Source of Truth
2. `AGENTS.md`
3. `GOAL.md`
4. `docs/current-work.md`
5. Latest section of `docs/ai-work-handoff.md`

## Current state

- Base main: `2f1749d4167d91d8c4d6d45ef0abdb3333bb00df` (PR #264 merged)
- Active work branch: `fix/v1-direct-evidence-voice-final-20260827`
- Keep the existing dirty worktree and do not reset, clean, rebase, or discard it.
- `.runtime/`, `.ai-tmp/`, credentials, tokens, cookies, and storage state are never committed.
- Active production accounts: `night_scout`, `liver_manager`, `beauty_account`.
- `tiktok_shop` remains `CREDENTIAL_PENDING` and must not receive a fabricated identity.

## Current implementation target

- Direct Media selection requires usable source text before external download cost.
- Stored Cloudinary media that only needs understanding refresh is preferred over a new network download.
- Caption, semantic, persona, or public-validator failures never quarantine physically valid media.
- Only narrowly proven legacy downstream false quarantines receive one bounded retry.
- Night Scout and Liver Manager Direct Media may become `READY` only through strict Hybrid AI, rights, permission, validator, internal-leak, account-fit, and media URL gates.
- Beauty remains human-review-only and is never included in autonomous READY promotion.
- Direct preparation never publishes. Scheduled publishers remain separately gated and bounded to one post.

## Validation baseline

- Direct Media focused tests: 46/46 PASS.
- Repository script regression: 876/876 PASS.
- Pytest suite: 146/146 PASS.
- V1 autonomous completion audit: 100/100 PASS.
- Workflow safety contracts: 504/504 PASS.
- Ruff fatal rules, compileall, source registry validation, and `git diff --check`: PASS.

## Exact next order

1. Commit this branch, push it, open one PR, and obtain exact-head CI success.
2. Merge normally and synchronize local `main` with `origin/main`.
3. Run Liver Manager Direct preparation in production and require a real non-empty `READY` queue ID with Sheets read-after-write.
4. Run the Liver Direct publisher in dry-run mode against that inventory.
5. Run Night Direct preparation; `READY` is accepted when eligible media exists, otherwise exact `NO_ELIGIBLE_MEDIA` is fail-closed.
6. Run Beauty preparation and require a reviewable `WAITING_REVIEW` candidate without fabricating approval.
7. Verify Night/Liver text dry-runs, active workflows, schedules, global config, and X publishing disabled.
8. Claim V1 completion only when every condition in the current Owner contract is backed by production evidence.

## Safety boundary

- Do not lower rights, provenance, permission, author, parent, account, semantic, persona, quality, or Hybrid AI gates.
- Do not bypass CAPTCHA/login challenges. External provider failures are bounded and fail-soft.
- Do not auto-promote Beauty.
- Do not publish to X.
- Do not describe a dry-run, mock, or software-only result as production proof.
