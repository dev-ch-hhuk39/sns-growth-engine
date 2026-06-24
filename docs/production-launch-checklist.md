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
- 投稿テキスト確定（99字）: ✅
  ```
  夜職で伸びる子に共通するのは、LINEの返し方が上手いこと。"また話したい"と思わせる会話ができる子は強い。学歴や見た目より、長く稼ぐには会話力が大事なんだよね。磨ける力だから、今からでも伸ばせる。
  ```
- media asset preflight: PASS ✅
- X publisher dry-run: DRY_RUN ✅
- Threads publisher dry-run: DRY_RUN ✅
- PDCA dry-run: 完了（pdca_8bcc26d2）✅
- 実投稿: **READY_WITH_MISSING_CREDENTIALS**（X/Threads 認証情報未設定）

不足認証情報:
- `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`（X投稿の場合）
- `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`（Threads投稿の場合）

## Threads 初回実投稿 (2026-06-23) ✅

- アカウント: night_scout (`@kyaba_consul_mizu`)
- post_id: `18127402414723102`
- posted_url: https://www.threads.com/@kyaba_consul_mizu/post/DZ6Drm5k9SL
- posted_at: 2026-06-23T00:00:00Z
- posted_results: result_id=`r-5da1d941`
- 修正: workflow env渡し漏れ / post_url生成 / is_dry_run_ok @property
- 詳細: `docs/threads-first-live-post-report.md` 参照

## Human Next Steps

1. 2026-06-25 以降: Threads インサイトで impressions/likes/replies 確認
2. posted_results の metrics_status を MEASURED に更新
3. PDCA 分析 → 次回投稿テキスト生成
4. X API: Developer Portal で Basic Plan 以上を契約（402 解消）
5. X 投稿: `data/manual_post_queue.json` (status=retry_ready) を使用
6. YouTube/TikTok clip pipeline: `docs/youtube-tiktok-clipping-runbook.md` 参照

## Consolidation Policy (2026-06-20)

旧3リポジトリと新 sns-growth-engine の並行運用は禁止。  
今後の運用は `dev-ch-hhuk39/sns-growth-engine` に一本化する。

### 旧リポジトリ停止状況

| リポジトリ | 対象 | 停止状況 |
|---|---|---|
| X_autopost_yoru | night_scout / X | [ ] 未停止 |
| threads_auto_post_gs | night_scout / Threads | [ ] 未停止 |
| threads-liver-coachhing | liver_manager / Threads | [ ] 未停止 |

### 本番投稿開始の前提条件

- [ ] 旧3リポジトリの GitHub Actions をすべて disable
- [ ] 各アカウントのタイムラインで意図しない投稿が停止したこと確認（24時間）
- [ ] `.env` に認証情報設定済み（THREADS_ACCESS_TOKEN は night_scout / liver_manager 別）
- [ ] publish_x_post.py または publish_threads_post.py で dry-run PASS
- [ ] real post は 1件ずつ・明示的承認のもとで実行

### 関連ドキュメント

- `docs/legacy-repo-migration-audit.md`: 旧 repo 詳細調査
- `docs/legacy-repo-shutdown-plan.md`: 停止手順
- `docs/credential-migration-plan.md`: 認証情報移行手順

## Sheets Recovery / Threads-first Operation (2026-06-24)

- [x] Google Sheets actual tabs audited.
- [x] Empty production tabs seeded.
- [x] Read-after-write verification passed: 21 / 21.
- [x] `night_scout` queue seeded: 3 Threads rows.
- [x] `liver_manager` queue seeded: 3 Threads rows.
- [x] `beauty_account` queue rows: 0.
- [x] CTA policy applied: night/liver `LINE_AND_DM`, beauty `NONE`.
- [x] X posting disabled for recovery mode.
- [x] Cloudinary upload not executed.
- [x] media download/cut/upload not executed.
- [x] transcription API not called.
- [x] `liver_manager` Threads real post executed once and recorded.
- [x] Threads queue worker implemented.
- [x] Metrics manual import CLI implemented.
- [x] Queue refill CLI implemented.
- [x] Manual-only GitHub Actions queue worker implemented.
- [x] Daily dry-run workflow switched to Threads-first queue dry-run.
- [x] True dry-run fixed: queue/refill dry-run do not call `setup_all()` or write.
- [x] GitHub Actions dry-run attempted and failure classified.
- [ ] Stricter live Sheets verify after queue worker release: blocked by local approval credits.
- [ ] Live queue worker dry-run for night/liver after queue worker release: blocked by local approval credits.
- [ ] GitHub Actions queue worker dry-run PASS: blocked until Sheets repository secrets are registered.

### Recovery Commands

```bash
python3 scripts/recover_production_sheets_threads_first.py --verify-only
python3 scripts/process_threads_queue.py --account-id night_scout --dry-run
python3 scripts/process_threads_queue.py --account-id liver_manager --dry-run
python3 scripts/refill_threads_queue.py --account-id night_scout --count 1 --dry-run
python3 scripts/refill_threads_queue.py --account-id liver_manager --count 1 --dry-run
python3 scripts/publish_threads_post.py --account-id night_scout --text "<text>" --dry-run
python3 scripts/publish_threads_post.py --account-id liver_manager --text "<text>" --dry-run
```

### GitHub Actions Dry-Run

Required repository secrets:

- `SNS_MASTER_SHEET_ID` or `SPREADSHEET_ID`
- `SA_JSON_BASE64` or `GCP_SA_JSON_BASE64`

Workflow inputs:

- workflow: `Threads Queue Worker`
- `account_id=night_scout`
- `mode=dry_run`
- `max_posts=1`
- `confirm_real_post=false`

### Recovery Docs

- `docs/sheets-recovery-report.md`
- `docs/sheets-manual-check-guide.md`
- `docs/cta-rules.md`
- `docs/threads-operation-runbook.md`
- `docs/threads-queue-worker.md`
- `docs/metrics-import-runbook.md`
- `docs/production-completion-status.md`
