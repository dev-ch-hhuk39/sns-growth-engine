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
