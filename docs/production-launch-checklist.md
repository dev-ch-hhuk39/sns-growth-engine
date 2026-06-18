# Production Launch Checklist

SNS自動投稿システム v2 の初回運用開始チェックリストです。

## Current Release

- PR: https://github.com/dev-ch-hhuk39/sns-growth-engine/pull/1
- Feature branch: `feature/codex-final-production-audit`
- Feature HEAD before docs rollout commit: `cfd31823f7ffb72f622d37bba9580e3284e2ac5b`
- Base: `origin/main` at `1edf83abc93623be83abe05bd0a9e12e2ff14d00`
- Status before merge: merge-ready after tests and dry-run/BLOCKED checks
- Merge result: PR #1 squash merged
- Production pipeline merge SHA: `759af859a4d70d9ec1105f8d70f1c4ea893f29db`
- main verification: minimum tests 4 / 4 PASS, dry-run / BLOCKED 5 / 5 PASS
- Follow-up PR: https://github.com/dev-ch-hhuk39/sns-growth-engine/pull/2
- Follow-up PR status: squash merged 2026-06-18 (SHA: `19b0b77148a38717b996fb6df40066a9f6267df8`).
- Pilot deploy: SMOKE PASS (night_scout/x, night_scout/threads, liver_manager/threads)
- Security fix: pipeline_store.py stage validation added (commit `6bb694b`)
- Follow-up fix: `run_real_smoke_plan.py --platform threads` uses Threads readiness checks.

## Merge Gates

- [x] PR created
- [x] Conflict-sensitive files reviewed
- [x] Diff limited to `config`, `docs`, `scripts`, and `src`
- [x] `.env`, cookie, token, API key, image/video artifacts not included
- [x] `.claude/plans/` not committed
- [x] Phase13 minimum tests PASS
- [x] Phase9-13 regression PASS
- [x] dry-run / BLOCKED checks PASS
- [x] no real fetch/download/cut/upload/post executed
- [x] `beauty_account` remains WAITING_REVIEW / draft-only
- [x] `learning_rules active=true` not introduced
- [x] source priority auto-change not introduced

## Source Candidate Gates

- [x] fixed user-provided URLs: 54 / 54
- [x] `night_scout`: 31 sources
- [x] `liver_manager`: 24 sources
- [x] `beauty_account`: 36 sources
- [x] query sources: 37
- [x] note/article sources: 6
- [x] all production candidates inactive
- [x] all production candidates fetch disabled
- [x] download/cut/upload defaults false

## Required First Smoke Order

1. tool doctor
2. source registry validate
3. source candidate review
4. mock fetch dry-run
5. source_to_post pipeline mock dry-run
6. media preflight dry-run
7. publisher dry-run
8. posted_results import dry-run
9. PDCA dry-run
10. human-approved confirm-fetch for one source only
11. no download/cut/upload/post after confirm-fetch
12. separate approval for download/cut/upload/post
13. first one-post smoke stops at publisher dry-run
14. real post requires another explicit approval

## Commands

```bash
python3 scripts/check_source_fetcher_tools.py --dry-run
python3 scripts/manage_source_accounts.py --validate --dry-run
python3 scripts/review_source_candidates.py --account-id night_scout --dry-run
python3 scripts/fetch_source_posts.py --account-id night_scout --platform x --mock --dry-run
python3 scripts/run_source_to_post_pipeline.py --account-id night_scout --platform x --mock --dry-run
python3 scripts/preflight_media_assets.py --account-id night_scout --mock --dry-run
python3 scripts/publish_x_post.py --account-id night_scout --confirm-post --dry-run
python3 scripts/import_posted_results.py --mock --dry-run
python3 scripts/run_pdca_cycle.py --account-id night_scout --platform x --days 7 --dry-run --mock --generate-next-plan
```

## BLOCKED Checks

```bash
python3 scripts/fetch_source_posts.py --account-id night_scout --platform x --fetch --dry-run
python3 scripts/download_media_assets.py --account-id night_scout --download --dry-run
python3 scripts/cut_video_clips.py --account-id liver_manager --cut --dry-run
python3 scripts/upload_media_assets.py --account-id night_scout --upload --dry-run
```

Each command must print `BLOCKED`.

## Remaining WARN

- Real smoke readiness may report NOT_READY until credentials are configured.
- Sheets test-write is intentionally not part of this automated rollout.
- Abstract base classes may still contain `NotImplementedError`.
- Legacy docs may reference older blocked real-post behavior.
- PR #2 may remain unmerged until GitHub connector credits/approval are restored or a human merges it.

## First Live Post Run (2026-06-18)

- 実 fetch: `src_ns_yt_cand_009` (@kyaba_camera) から6件取得済み ✅
- 投稿テキスト: 生成済み（123字、スカウト視点、夜職女性向け）✅
- preflight: PASS ✅
- publisher dry-run: DRY_RUN ✅
- PDCA dry-run: 完了（pdca_8bcc26d2）✅
- 実投稿: **READY_WITH_MISSING_CREDENTIALS**（X/Threads 認証情報未設定）

不足認証情報:
- `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`（X投稿の場合）
- `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`（Threads投稿の場合）

## Human Next Steps

1. `.env` に X または Threads 認証情報を設定する
2. `python3 scripts/publish_x_post.py --account-id night_scout --confirm-post --dry-run` で再確認
3. `ALLOW_REAL_X_POST=true` を `.env` に追加（永続コミット禁止）
4. 初回実投稿を実行（text-only、1件のみ）
5. posted_results に登録し、PDCA を実データで再実行
