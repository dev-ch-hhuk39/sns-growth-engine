## 2026-09-10 Verification Read Repair

- PR #295 merged normally as `b79a55635a37351d120bc12b08276701dfce1820`; exact-head CI `34446569171` passed PR gate and regression tests.
- Real Night/Beauty preparation failed in the whole-Sheets verifier with read quota 429. All 18 verification tabs and existing checks are retained; a fresh bounded-retry batch snapshot replaces 18 un-retried individual reads. No cached pre-write evidence is reused.
- Live read-only verification with this patch: 63 checks PASS, zero failures (`--verify-only --text-inventory-scope`). No Sheets writes or posts during this verification.
- Direct preparation `34445439141` completed `MEDIA_INVENTORY_LOW` for all three accounts. Evidence/grounding, source suitability and caption-provider failures remain; no media PASS is claimed.
- Clip recheck `34449801739` on main passes numeric-zero range selection, but three Liver candidates then fail final caption review; none became READY or posted. Buffered activation stays OFF pending actual inventory and delivery proof.
- The saved-clip caption generator still used GitHub Models alone. It now shares the existing privacy-bounded Gemini failover with direct media. Gemini availability errors may try the existing secondary model once; auth/schema/budget failures do not model-hop. All downstream grounding/persona/alignment gates remain mandatory. Provider status codes are redacted, and the response schema explicitly describes internal analysis fields.

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

## Historical Work (Superseded by 2026-09-10 Scope)

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

# Current Work

status: V1_FINAL_DIRECT_MEDIA_PR_READY
assigned_agent: Codex
branch: fix/v1-direct-evidence-voice-final-20260827
base_main: 2f1749d4167d91d8c4d6d45ef0abdb3333bb00df
scope: finish strict autonomous Direct Media READY for Night Scout and Liver Manager, retain Beauty human review, then prove production E2E
working_tree: intentional implementation changes plus untracked runtime data; never reset or clean
production_operations: after normal merge, bounded preparation and read-after-write verification; Direct publisher dry-run only for this acceptance

## Completed locally

- Liver deterministic evidence caption produces canonical female-manager voice while preserving source claims.
- Stored uploaded media requiring understanding refresh is prioritized ahead of new external acquisition.
- Source posts without usable original text are rejected before network/download cost.
- Downstream caption/alignment/persona/public validation failures are separated from physical media failures.
- Legacy downstream-only false quarantine and pre-fix blocked queues have bounded one-time recovery.
- Direct preparation promotes at most one strict Hybrid-approved Night/Liver candidate to READY.
- Autonomous READY CLI requires explicit apply confirmation and performs no publishing.
- Beauty is structurally excluded from autonomous READY and remains human-review-only.
- Direct Media focused tests 46/46, repository tests 876/876, pytest 146/146, completion audit 100/100, workflow safety 504/504 PASS.

## Remaining sequence

1. Commit/push/PR/exact-head CI/normal merge/main sync.
2. Liver production Direct preparation: require `READY`, non-empty queue ID, and Sheets read-after-write.
3. Liver Direct scheduled publisher path: dry-run only.
4. Night production Direct preparation: READY when eligible, otherwise exact fail-closed reason.
5. Beauty preparation: reviewable WAITING_REVIEW only.
6. Night/Liver text route dry-runs, active workflow/schedule/config audit.
7. Final evidence report; only then decide whether the Owner's V1 completion sentence is truthful.

## Do not do

- Do not weaken safety, rights, permission, provenance, account, persona, semantic, quality, or Hybrid AI gates.
- Do not auto-approve Beauty or publish to X.
- Do not commit `.runtime/`, `.ai-tmp/`, secrets, tokens, cookies, or storage state.
- Do not claim production evidence from local tests or dry-runs.
