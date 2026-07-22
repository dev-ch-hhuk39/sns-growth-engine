# Goal Completion Implementation Plan

## Purpose And Stop Line

This document is the executable handoff for completing the 35-item Goal in
`config/goal_acceptance.json`. The audit was performed on branch
`feature/oss-github-actions-media-autopilot` at implementation HEAD
`026ed40b65d2c708673313286c8bc9a914b1efe7` against `origin/main`
`f89f6ed44bc2a00930f04601d5700230e25949d3` on 2026-07-22 JST.

The current high-capability-model task stops after this design. Do not treat
this document as a production completion claim. The implementation model must
continue until `python3 scripts/evaluate_goal.py --json` reports exactly
`35/35 PASS`, the change is merged to `main`, `origin/main` matches, and all
four production canaries have independently verified evidence.

## Audited Truth

- Working branch and its remote are synchronized and the worktree was clean
  before this documentation update.
- PR #3 is open and mergeable, but its three CI jobs failed before any steps
  started. This is an infrastructure/startup failure, not a test failure.
- The repository is private. Publicization is a separate, irreversible-impact
  human-approved operation because it exposes the complete Git history.
- `production` Environment and protected-main enforcement were not available
  in the last successful API audit. Do not claim secret environment protection
  until both are re-checked after repository publicization.
- All production workflows in this branch use `ubuntu-latest`; workflow scans
  found no `self-hosted` or VPS runner dependency.
- Official gitleaks 8.30.1 scanned 168 commits on 2026-07-22 and found no leak.
- Local repository tests pass 629/629; compileall passes. Ruff and mypy were
  not re-run in the current local interpreter because those optional CI tools
  are not installed there. CI installs their exact pins from
  `requirements-ci.txt` and must provide final evidence.
- Sheets production integrity was previously reconciled and the full verifier
  passed 63/63 with `posted_save_failed_count=0`; this must be re-run after the
  final merge and before canaries.
- Real source research persisted five bounded results in each of the four
  research tables. Agent-Reach doctor and last30days preflight passed.
- Approved acquisition reached real YouTube metadata, then exposed a Google
  Sheets 50,000-character transcript-cell failure. The acquisition runner now
  bounds transcript rows, but the independent transcription runner still does
  not call the same normalizer.
- TikTok discovery still has real rehydration failures. Fallback routing is
  implemented and tested, but requires a bounded live canary after merge.
- There is no Goal-qualified READY media inventory for either direct media or
  generated clips. Old production inventory is not accepted as Goal evidence.
- There is no registered third-party Threads source account URL for
  `liver_manager`. The posting account URL is not silently reclassified as a
  source. This is an allowed external blocker unless the user supplies or
  explicitly approves a source account URL.
- `docs/goal-status.json`, `docs/runtime-health.json`, and
  `docs/goal-evidence.md` were stale baseline documents before this audit.

## Acceptance Snapshot

`PASS` below means the implementation and evidence currently satisfy the
criterion. `UNVERIFIED` means code exists but final-main/live evidence is
missing. `BLOCKED` means a permitted human or platform operation is required.

| Criterion | Audit status | Required final evidence |
| --- | --- | --- |
| repository_public | BLOCKED | Public GitHub URL and visibility timestamp |
| secret_history_scan | PASS | gitleaks 8.30.1, full 168-commit scan, run time |
| production_secrets_private | UNVERIFIED | Secret names only plus protected `production` Environment |
| github_hosted_only | PASS | Workflow scan and `ubuntu-latest` label |
| no_vps_or_self_hosted_dependency | PASS | Zero workflow/runtime dependency references |
| working_tree_clean | PASS | Clean status at audited implementation HEAD; repeat at final HEAD |
| origin_main_matches | FAIL | Final local HEAD equals fetched `origin/main` |
| agent_reach_integrated | PASS | Exact version/SHA, doctor result, adapter path |
| last30days_integrated | PASS | Exact version/SHA, preflight/smoke result, adapter path |
| youtube_backends_integrated | PASS | yt-dlp, transcript API, comments provider contracts |
| tiktok_multiple_backends_integrated | PASS | Primary/fallback/bounded-limit tests; repeat live canary |
| threads_multiple_backends_integrated | UNVERIFIED | Primary/fallback plus live result on final `main` |
| web_fallback_integrated | PASS | Agent-Reach WebChannel/Jina smoke result |
| library_capability_matrix_complete | PASS | Matrix, license audit, exact version/revision pins |
| night_account_url_discovery | UNVERIFIED | Account URL, real source post URL and ID |
| night_source_bundle | UNVERIFIED | Same-post text hash, media ID, parent-integrity PASS |
| night_direct_media_post | UNVERIFIED | New Threads permalink and Cloudinary media evidence |
| night_generated_clip_post | UNVERIFIED | New permalink, Cloudinary URL, clip candidate ID |
| night_caption_alignment | UNVERIFIED | Alignment threshold PASS and unsupported claims = 0 |
| liver_account_url_discovery | BLOCKED | Human-approved Threads source account URL and real post |
| liver_source_bundle | UNVERIFIED | Same-post text hash, media ID, parent-integrity PASS |
| liver_direct_media_post | UNVERIFIED | New Threads permalink and Cloudinary media evidence |
| liver_generated_clip_post | UNVERIFIED | New permalink, Cloudinary URL, clip candidate ID |
| liver_caption_alignment | UNVERIFIED | Alignment threshold PASS and unsupported claims = 0 |
| permission_single_authority | PASS | Sheets `media_permissions` authority and contradiction tests |
| backend_failover | PASS | Routing tests and backend routing rows |
| asset_quarantine | PASS | Quarantine tests and a bounded failure record |
| next_candidate_selection | PASS | Selection tests and next-candidate evidence |
| schedule_delay_recovery | UNVERIFIED | Tests plus final-main Actions run ID |
| slot_idempotency | PASS | Tests plus reconciled slot evidence; repeat final verifier |
| sheets_evidence | PASS | 63/63 production verifier and zero save failures; repeat final |
| cloudinary_idempotency | UNVERIFIED | Test plus Goal-specific asset/public ID evidence |
| text_fallback | PASS | Fallback and READY-gate tests |
| text_pipeline_regression_free | UNVERIFIED | One verified final-main result per account |
| all_required_tests_pass | UNVERIFIED | Local + GitHub CI PASS at final `main` |

Current audit classification is 17 PASS, 16 UNVERIFIED/FAIL, and 2 BLOCKED.
The fail-closed evaluator remains the authority; no manual status promotion is
allowed without the required evidence keys.

## Implementation Rules

1. Make one bounded change at a time. Run its named tests before continuing.
2. Never weaken `final_public_post_validator`, media rights gates, source-post
   parent integrity, unsupported-claim checks, or slot idempotency.
3. Sheets `media_permissions` is the sole runtime permission authority. Repo
   config may make a source discoverable, but cannot grant media reuse.
4. A permission row must be active, unexpired, unrevoked, evidence-bearing,
   and explicitly allow the requested operation.
5. X and `beauty_account` stay blocked. No secret value, cookie, storage state,
   `.env`, `data/`, or `output/` may be committed or logged.
6. Source discovery, preparation, posting, and evidence evaluation remain
   separate workflows. A posting workflow never discovers or edits media.
7. A successful workflow conclusion is not proof of a post. PASS needs Sheets,
   Cloudinary, Threads permalink, and read-after-write verification together.
8. Never use old production posts or assets as the four Goal canaries.
9. Maximum real canaries: one direct-media and one generated-clip post for each
   account. Stop immediately after each post for independent verification.
10. Burned-in subtitles remain disabled per the user's explicit instruction.

## Work Package 1: Close Code Gaps

### 1.1 Normalize every transcript write

Files:

- `scripts/transcribe_approved_source_videos.py`
- `src/transcription/sheets_limits.py`
- `scripts/test_transcript_sheets_cell_limits.py`

Steps:

1. Import `normalize_transcript_row` in the independent transcribe runner.
2. Apply it immediately before every Sheets append/update of
   `video_transcripts` rows, not only in account acquisition.
3. Preserve the full transcript SHA, first/last evidence, chunk count, and
   `SHEETS_BOUNDED` scope marker. Do not log full transcript text.
4. Add a regression test that passes a transcript and segment payload over
   50,000 characters through the transcribe runner persistence boundary.

Acceptance:

- Every cell is at most 49,000 characters.
- Hash and non-empty head/tail evidence survive normalization.
- Dry-run writes nothing.

### 1.2 Harden yt-dlp execution without unbounded scraping

Files:

- `src/acquisition/ytdlp.py`
- `src/acquisition/tiktok_public.py`
- `scripts/discover_approved_source_videos.py`
- `requirements-acquisition.txt`
- related provider tests

Steps:

1. Use the configured Node JS runtime on all yt-dlp routes.
2. Add the pinned/approved EJS remote component option only where yt-dlp needs
   it for YouTube extraction. Keep exact dependency pins and bounded limits.
3. For TikTok, route a rehydration failure to the next registered backend.
   Account/profile discovery stays bounded; no login bypass and no profile
   expansion loop.
4. Emit provider name, version, retryability, attempt count, and final reason
   into `provider_runs` and `backend_routing_history`.

Acceptance:

- Unit tests cover primary failure, fallback success, all-backends failure,
  limits, and redacted output.
- Unknown/third-party-reference-only sources never reach download.

### 1.3 Make evidence generation mechanical

Files:

- `scripts/evaluate_goal.py`
- `docs/goal-status.json`
- `docs/runtime-health.json`
- `docs/goal-evidence.md`

Steps:

1. Add or reuse a read-only evidence collector that produces candidate status
   from git, workflow scans, test JSON, Sheets verification JSON, and canary
   records. It must never infer PASS from prose.
2. Require the exact fields in `config/goal_acceptance.json`.
3. Keep final promotion explicit and fail closed when any evidence is missing,
   stale, from a different commit, or from a different source-post bundle.

Acceptance:

- A fixture with one missing evidence field fails.
- A stale commit SHA fails.
- A complete 35-item fixture passes.

### Work Package 1 verification

```bash
python3 scripts/test_transcript_sheets_cell_limits.py
python3 scripts/test_ytdlp_node_runtime_configured.py
python3 scripts/test_tiktok_multiple_backends_integrated.py
python3 scripts/test_provider_contracts.py
python3 scripts/test_provider_registry_capabilities.py
python3 scripts/run_repository_tests.py --json-output /tmp/repository-tests.json
python3 -m compileall -q src scripts
git diff --check
```

## Work Package 2: Infrastructure Gate

This package contains external writes. Do not execute it silently.

1. Re-run full-history gitleaks on the exact merge candidate.
2. Ask for one explicit approval to make the repository public. State that the
   complete Git history becomes publicly visible.
3. After approval only, set visibility to public and verify it read-only.
4. Create a `production` Environment restricted to protected `main`. It must
   have no required reviewers because scheduled runs are approval-less.
5. Protect `main`: require PR, require all CI checks, disallow force pushes and
   deletion. Preserve administrator safety according to repository policy.
6. Re-run PR #3 CI. Investigate actual job logs if a job starts and fails.
   A runner-start failure is not a test result.
7. Merge only after CI, dependency audit, license checks, and history scan pass.
8. Fetch and verify local HEAD equals `origin/main`.

Acceptance:

- Public visibility is confirmed by GitHub API.
- `production` Environment and protected `main` are confirmed by API.
- CI has executed steps and all required checks pass at the merged SHA.
- No branch bypass, force push, or direct unreviewed code merge is used.

## Work Package 3: Final-Main Data And Provider Verification

Run on final `main`, with posting flags false.

1. Verify Sheets schema and production integrity read-only.
2. Seed/update owner-attested permission rows only when evidence exists; never
   revive a revoked row.
3. Run bounded source research for both accounts and confirm new rows are
   idempotent.
4. Run approved account acquisition for Night Scout and permitted
   YouTube/TikTok sources. Confirm same-post bundles and transcript limits.
5. For Liver Manager Threads discovery, search existing Sheets/config/history.
   If no source account URL exists, record the external blocker and do not
   invent or silently repurpose an account.
6. Validate live Threads primary/fallback routing and bounded TikTok fallback.
7. Re-run the 63-check production verifier and require 63/63.

Required evidence:

- Workflow run IDs and final commit SHA.
- Provider routing rows with no secret/body leakage.
- Source account URL, source post URL/ID, text hash, ordered media rows, and
  parent-integrity PASS for each selected source bundle.
- `posted_save_failed_count=0` and no duplicate slot/queue row.

## Work Package 4: Build Goal-Specific Media Inventory

Posting remains false throughout this package.

For each account, prepare exactly:

- one validator-approved direct-media asset from a single source post; and
- one transcript/metadata-grounded generated clip candidate.

Direct-media rules:

1. Select one active permission-ledger source and one real source post.
2. Keep text and every media item bound to the same source post ID.
3. Download/upload only under the preparation workflow's scoped env gates.
4. Preserve carousel order and media type.
5. Run OCR/ASR/content understanding and generate source-grounded public text.
6. Require semantic alignment PASS and unsupported claim count zero.

Generated-clip rules:

1. Select one approved individual source video per account.
2. Use transcript/comment/metadata signals to choose a non-overlapping clip.
3. Cut without burned-in subtitles, upload idempotently, and register one
   `MEDIA_READY` asset.
4. Quarantine a failing asset and select the next candidate; never loop forever.

Acceptance:

- Inventory checker reports direct=1 and generated_clip=1 for each account.
- Every asset has permission evidence, Cloudinary public ID and secure URL,
  content hash, parent source ID, alignment evidence, and unused status.
- No post has occurred.

## Work Package 5: Four Production Canaries

Prerequisites: Work Packages 1-4 PASS, final-main CI PASS, 63/63 Sheets verifier,
valid Threads tokens, and the evaluator has no unrelated failing criteria.

Order:

1. Night Scout direct media.
2. Verify post text and actual media, then Night Scout generated clip.
3. Liver Manager direct media.
4. Verify post text and actual media, then Liver Manager generated clip.

For each canary:

1. Dispatch the account/path-specific posting workflow with one slot and one
   asset. Keep `max_posts_per_run=1`.
2. Read the public Threads permalink and confirm the real media type/content.
3. Read back `queue`, `posted_results`, media asset, slot run, and provider
   evidence. Check the Cloudinary URL is the exact posted asset.
4. Record all fields required by section 25 of the Goal specification.
5. If validation fails, mark the post/candidate failed, quarantine the asset,
   stop further canaries, and fix the root cause before retrying. Do not repost
   the same asset/text.

No criterion passes merely because the workflow is green or a URL exists.

## Work Package 6: Final Evaluation And Merge Closure

1. Run the full local suite, compile, Ruff, mypy, license audit, dependency
   audit, workflow safety tests, and full-history gitleaks.
2. Run final-main GitHub CI and library health workflows.
3. Run the production Sheets verifier and read all four canary records.
4. Update `docs/goal-status.json`, `docs/runtime-health.json`, and
   `docs/goal-evidence.md` from machine-readable evidence.
5. Run `python3 scripts/evaluate_goal.py --json`. Require 35/35 PASS.
6. Confirm clean worktree and fetched `origin/main == HEAD`.
7. Only then mark the active Goal complete and report final usage.

## Stop Conditions And Human Input

Stop and report one consolidated human-action request when any of these occurs:

- Publicization approval has not been explicitly granted.
- No Liver Manager Threads source account URL exists anywhere.
- A Threads token requires reauthorization.
- A full-history leak requires external key rotation.
- Source acquisition requires a dedicated read-only login/cookie.
- A required source lacks a valid permission-ledger row.

Do not label the Goal complete while any stop condition remains.

## Low-Cost Model Operating Instructions

The implementation model should begin at Work Package 1, read this document,
`GOAL.md`, `config/goal_acceptance.json`, and the latest
`docs/ai-work-handoff.md`, then inspect only the files named in the active work
package. It should update this plan's checklist and the handoff after every
checkpoint. It must not redesign the architecture unless a test proves the
design impossible.

Recommended model: **GPT-5.6 Terra** with **medium reasoning**. Use low
reasoning only for deterministic reruns, documentation synchronization, and
mechanical formatting after tests are green. Return to a highest-capability
model only for a new architecture conflict, security incident, irreducible
provider failure across all bounded fallbacks, or ambiguous evidence that could
cause an incorrect real post.
