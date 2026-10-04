## 2026-10-04 Smoke relevance quota observability

- Base `4dc2293178f9e1488e1acf9014b6934c3420154e`, branch `feat/content-quality-v2`. Run `37130659799` proved Night Vision (503 -> 200, empty visible_action accepted); relevance ended HTTP 429 after three attempts without quota/history evidence. This patch targets only the Smoke relevance provider path.
- `generate_json(retry_profile="vision_relevance")` reuses existing safe quota metadata and `vision_retry_decision`: daily/zero stop, spend/>60-second delay defer, provider delay preferred, unknown 429/503 bounded to three total attempts. The default profile keeps its prior retry behavior, cache format and return shape.
- Success and failed exceptions preserve attempt history; cache hits return zero attempts and an empty current-call history. The Smoke-specific wrapper passes allowlisted diagnostics and history to its review package without modifying business relevance rules or the shared content-quality result contract. Existing relevance decision class remains separate from provider failure evidence.
- Vision multimodal implementation is AST-identical to base. No changes to Vision schema/prompt/model, media facts/binding, relevance criteria, angles, caption quality, rights, production workflows, scheduler, queues or posting.
- Validation: focused 87/87 PASS (new relevance tests 9, existing quota/Vision/Smoke/client/media tests 78). Workflow Safety 527/527 PASS (one run), compile and Ruff fatal checks PASS. Full repository suite: 938/938 scripts PASS, exactly one run (standard 8 external probes and 3 optional-tool probes excluded). Diff check PASS.
- One local commit only; no push, Smoke dispatch, real API request or production data operation. Preserve `.runtime/` and the four pre-existing untracked audit Markdown files.

## 2026-10-03 Gemini quota diagnostics and selected-account Smoke

- Base `09c6871116924ce164a1e93e2c337d8dabe6b636`, branch `feat/content-quality-v2`. Run `36971863378` hit Vision HTTP 429 after three attempts for each account; relevance/caption never ran, and all production jobs skipped. This change does not establish the live quota cause.
- Preserve allowlisted structured QuotaFailure/RetryInfo metadata and safe Vision attempt history. Raw error messages/subjects, project/user/billing dimensions and unknown identifiers are omitted. Six evidence-based quota classes; no inference from free-text messages. Unknown field values stay empty.
- Vision only: daily quota or explicit zero quota stops after one attempt; spend and provider delays over 60 seconds defer. Otherwise use provider retryDelay when available, fallback 5/15 seconds, maximum three total attempts (including unknown 429). Existing text/relevance/caption retry policy and model selection are unchanged. GeminiHttpError retains only safe metadata rather than raw error text.
- Smoke accepts existing target_account via a quoted environment variable: Night/Liver/Beauty individually or all. Target counts/success are scoped to selected previews; existing relevance/caption fail-closed conditions remain intact. Production job blocks and all content, visual-fact, permission and publish contracts are unchanged; model remains gemini-3.5-flash.
- Read-only audit: `docs/GEMINI_QUOTA_WORKFLOW_AUDIT.md` inventories 21 workflows and 41 directly referencing scripts/modules. Nominal AUTO_READY cron is 06:07 UTC near the run, but actual overlap is UNKNOWN. API returned two scheduled runs created within +/-15 minutes, both skipped. No quota causality inferred.
- Validation: focused 78/78 checks PASS (quota 12, Vision 23, Smoke 8, Media-first 16, understanding 7, client 12); full repository suite 937/937 scripts PASS, exactly once (standard 8 external and 3 optional-tool probes excluded). Workflow Safety 527/527 PASS; actionlint, compile, Ruff fatal rules and diff checks PASS.
- One additional local commit only. No push or Smoke/API execution, code deployment, production data operations or model fallback added. Preserve `.runtime/` and the four pre-existing untracked audit Markdown files; only the new quota audit is included.

## 2026-10-01 Static visual facts and relevance evidence (active)

- Base `2457716cd6d1427cb4e5e84275a7003b147b9068`, branch `feat/content-quality-v2`; bounded corrections from run `36785573938` only. No production operations or Smoke execution.
- `visible_action` remains a required string key but may be empty. Summary/key moment/nonempty facts/schema/HTTP/frame evidence and asset/hash binding remain required; no action is invented for static media.
- Strict relevance maps every requested fact type to actual verified facts and emits their IDs; action facts are not mandatory. Unknown/missing anchors, mismatched accounts or missing reader/pillar/reason remain unverified. Selected angle evidence uses the actual matched fact text.
- Preserve relevance review status, reason, audience need, pillar, requested fact types, provider status/HTTP/error and decision class. Provider failure is not semantic rejection; Vision and Relevance attempts are separately reported.
- Vision and opt-in relevance text requests retry only 429/503 or transient transport failures, at most three total attempts with 5/15-second waits. Default text/caption retry behavior and production workflows remain unchanged.
- Focused tests PASS: Gemini/static/relevance 23/23, Smoke 8/8, Media-first 16/16, understanding contract 7/7; workflow safety 527/527; Ruff/compile/diff checks PASS. Final full repository suite 936/936 PASS (one run; saved result confirmed on 2026-10-02). No live Smoke or production operations performed.
- Commit locally only. No push, dispatch, merge, deploy, posting, READY, Sheets write, Cloudinary or acquisition. Preserve `.runtime/` and untracked audit Markdown files.

## 2026-09-30 Vision response diagnostics (active)

- Base `73e976a4a9348854859710e97a91b65adc5df326`; branch `feat/content-quality-v2`. Previous smoke `36712822605`: Night HTTP 200 with invalid visual evidence, Liver/Beauty HTTP 503; all production jobs skipped, no captions.
- Scope is Vision response processing only: exact JSON object or complete JSON fence, fixed `visible_actions` alias normalization, required observation fields, safe missing/type/empty/duplicate-fact diagnostics. No response bodies or arbitrary response values enter error output. Vision HTTP/JSON/schema/visual-evidence stages remain distinct from existing relevance/caption counters.
- Multimodal requests retry only HTTP 503 or transient transport failures, at most two retries with 5/15-second delays. Every attempt uses the existing budget reservation; 4xx and schema errors never retry. Text-only transport behavior, account relevance, caption generation and workflow configuration are unchanged.
- Validation: Gemini Vision 16/16, Smoke 8/8, Media-first 16/16 and understanding contract 7/7 PASS; full repository suite 936/936 PASS (one run); Ruff fatal rules, compileall and diff check PASS. Real API behavior remains untested in this change. One local commit only; do not push or dispatch. No production posting, READY, Sheets, Cloudinary, acquisition or scheduler changes. Preserve `.runtime/` and the four untracked audit Markdown files.

## 2026-09-29 Gemini Vision migration (active)

- Base `167cf1126eed46e115741da6f765bf20fe294bb9`, branch `feat/content-quality-v2`. Previous authorized push succeeded; smoke run `36537637253` failed all three Vision requests with `INVALID_RESPONSE`; all three production jobs skipped. This supersedes the old push-blocked note below.
- Replace retired GitHub Models Vision with existing Gemini GenerateContent infrastructure, default `gemini-3.5-flash` (override `GEMINI_VISION_MODEL`, then `GEMINI_GENERATOR_MODEL`). No new key, provider account, or retired-provider fallback.
- Vision receives only up to three inline JPEG frames, observes facts, validates JSON, and records secret-free HTTP/schema/error evidence. Verified facts are asset/hash-bound. Relevance runs separately after Vision PASS; irrelevant media produces no caption. Existing Gemini caption path accepts selected visual fact IDs; text-only behavior is unchanged.
- Smoke receives only the existing Gemini secret, no production environment, and all production jobs remain explicitly skipped. Frames/cache/budget stay runner-temp. Preview assets remain the same three historical URLs; no acquisition, upload, READY, Sheets write, posting, deploy, merge, reset or force push.
- Validation: Media focused 212/212 PASS; Gemini Vision 8/8 and Smoke 8/8 PASS; Media-first order 16/16 PASS; workflow safety 527/527 PASS; Ruff fatal rules, compileall and diff check PASS. One full repository run checked 936 scripts: 935 passed, with only the obsolete "GitHub Models vision wired" source assertion failing. Updated that contract to require Gemini multimodal wiring and no retired endpoint; its focused rerun passed 7/7 checks. No runtime changes followed the full run. Full suite was not repeated under the one-run limit. All 936 scripts now have passing evidence, but the original full-run result is recorded as 935/936, not relabeled. Single post-push Gemini smoke remains pending; report Vision, relevance and caption counts separately.
- Preserve `.runtime/` and the four unrelated untracked audit Markdown files. They must not be staged.

## 2026-09-29 Content Quality V2 Vision Smoke (active)

- Branch `feat/content-quality-v2`; baseline HEAD `8a5c730ca02a1c3e2103726c992a51c79a4682fe`.
- Scope: exactly one existing historical preview each for Night, Liver and Beauty; read-only download, existing GitHub Models Vision, unpublished editorial caption review. No new media discovery, provider or credential.
- `FULL_SUITE_BEFORE=934/934 PASS` on a clean temporary export of the baseline commit (8 external credential/network probes and 3 optional local-tool probes excluded by the repository runner).
- Stable asset/hash-bound visual facts and selected angle fact IDs support natural caption paraphrases through the existing claim alignment verifier. Generic captions cannot count as successful media packages.
- Editorial review can draft with unverified rights; production eligibility and publication gates remain blocked. Smoke job has no production environment or production secrets; every other workflow job explicitly skips when smoke=true.
- Validation: Media focused 212/212 scripts PASS; Smoke 9/9 cases PASS; final full repository suite 935/935 scripts PASS; workflow safety 527/527 PASS; Ruff fatal rules, compileall and diff check PASS. Code commit `167cf1126eed46e115741da6f765bf20fe294bb9` is local only. Automatic approval review rejected the normal push twice because it requires direct approval of the public destination `dev-ch-hhuk39/sns-growth-engine` and payload, rather than accepting the attached instructions. Explicit approval has been requested. No workflow dispatched, no real Vision/caption result, no review artifact; real-media quality is NOT proven. After approval, push `feat/content-quality-v2`, then dispatch `gh workflow run direct-media-preparation.yml --repo dev-ch-hhuk39/sns-growth-engine --ref feat/content-quality-v2 -f content_quality_v2_vision_smoke=true -f confirm_preparation=false -f target_account=all`. Preserve `.runtime/` and unrelated untracked review documents.
- Never merge/deploy, promote READY, mutate production Sheets/permissions, publish or upload to Cloudinary for this task.

# SNS Growth Engine - Current Work

Updated: 2026-09-27

## Current task

- Latest locally confirmed `origin/main` / closure base: `3818e38fdd04185c9f2b70cda73daf2fe22b2f35`; branch `fix/production-supply-loop-closure`.
- Objective: close verified text/media supply-loop defects without architecture redesign or relaxing rights, quality, publisher, duplicate, account-isolation, X-posting or 80% host-disk guards.
- Local changes: delivery-first text replenishment; bounded theme retries; uploaded Direct assets needing understanding refresh before external acquisition; strict missing `source_videos` lineage repair; batched preparation snapshot includes `social_derivatives`.
- Stored-source Clip fallback uses an independent GitHub-hosted runner. Xserver heavy preparation remains blocked above 80%; posting/transcription API gates remain off in preparation.
- Validation: repository scripts 929/929 PASS; workflow safety 522/522 PASS; source registry validation PASS; focused contracts, Ruff, compileall and diff check PASS.
- Production Sheets writes, inventory generation, download/cut/upload and posting were not performed. The owner-supplied live evidence still reports Xserver disk 81.64% and previous text/direct/clip shortages.
- GitHub DNS currently fails (`Could not resolve host: github.com`), so push/PR/CI/merge/deploy and production recovery are pending. Preserve untracked `.runtime/` exactly.

## Evidence and limits

- Focused contracts, 923/923 repository regression, Ruff fatal rules, Python compilation, workflow YAML parsing, source registry validation, 116-check completion audit, 509 workflow safety checks, workflow permissions/capability registry, and `git diff --check` passed for PR #346. PR #347 checks passed. Exact-head CI for the pip bootstrap fix remains pending.
- Live pre-change read-only snapshot: Xserver disk 72.31%, preparation permitted. Text READY coverage calculation was wrong (58.33%) because it counted media slots; observed text slots were all covered. Actual publisher dry-runs showed Night Direct/Clip 3/3, Liver Direct/Clip 4/3, Beauty Direct 3. Evergreen bank Night/Liver/Beauty 50/30/50. Current-scope duplicate, unverified and missing-metrics counts were zero; legacy audit remains separate and unchanged.
- Required repository secret NAMES for Cloudinary/Gemini are present. Deploy `36112819390` failed on the line-count check; PR #347 fixed it. Deploy `36113687899` passed env validation but pip 22.0.2 hit an internal resolver AssertionError while installing media requirements. Current release/cron remain unchanged; runtime.env is mode 0600 and contains the authorized deployment variables. A pinned pip bootstrap fix is pending.
- No media cleanup, historical Sheets mutation, publish, Cloudinary upload or manual post was initiated during local implementation. Natural replenishment remains unverified until an Xserver cron run follows deployment.
- Preserve untracked `.runtime/`; never stage, clean, or delete it.

## Next steps

1. Merge the pinned pip bootstrap follow-up after required CI.
2. Deploy latest main to the existing Xserver runtime and verify runtime revision, cron, service, disk and secret presence (presence only).
3. Run read-only production readiness; then verify a natural Xserver preparation cycle refills routes to their minimums. Manual dispatch is not natural-run evidence.
4. Verify Text 72-hour coverage, evergreen reserve, current duplicate/unverified counts, read-after-write, metrics and PDCA without altering historical evidence.
5. Claim `FULL_SCHEDULE_PRODUCTION_COMPLETE=YES` only if every requested production condition is evidenced; otherwise list the exact external/runtime blocker.

## Safety

- Never publish from preparation; never post to X or Beauty outside existing account gates.
- Never weaken rights/provenance, persona/quality, account isolation, duplicate/idempotency, read-after-write, or kill-switch checks.
- Do not remove production data, assets, queues, evidence, logs, credentials, current release, or `.runtime/`.
