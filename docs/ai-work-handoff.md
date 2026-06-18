# AI Work Handoff

Codex / Claude Code 並行開発用の引き継ぎ資料です。主要作業完了時は必ず更新してください。

## 最終更新

- Date: 2026-06-16
- 作業AI: Codex
- 作業ブランチ: `feature/codex-final-production-audit`
- 作業ディレクトリ: `/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2`
- GitHub repo: `dev-ch-hhuk39/sns-growth-engine`
- 監査開始 HEAD: `1edf83abc93623be83abe05bd0a9e12e2ff14d00`
- 監査開始 origin/main: `1edf83abc93623be83abe05bd0a9e12e2ff14d00`

## システム概要

3アカウント（`night_scout` / `liver_manager` / `beauty_account`）向けの SNS 自動投稿支援システムです。

```
Source candidates
-> fetch / article normalize / buzz score
-> reference_posts
-> media_assets / video understanding / clip plans
-> generation_jobs / drafts / queue candidates
-> media preflight / publisher plan
-> posted_results candidates / PDCA suggestions
```

この Phase 13 監査では、実 fetch / download / cut / upload / post は一切実行していません。

## 今回の作業内容

- Claude Code 実装の Phase 13 production readiness を最終監査。
- `production_sources.example.json` の `REPLACE_WITH_REAL_*` を全削除し、ユーザー提供 URL 54件を登録。
- query source 37件を追加。
- `default_sources.json` の old example URL と active/fetch enabled を除去。
- media asset storage / preflight / download / upload 導線を追加。
- video clip executor 導線を追加。
- PipelineStore を Phase 13 保存対象、dry-run、Sheets write plan、queue status safety に対応。
- source-to-post orchestrator に media_assets / media_preflight / clip_candidate_plans を接続。
- publisher / review / import / smoke plan CLIs を指定 dry-run コマンド互換に補強。
- Phase 13 production path と media/query/article/publisher/PDCA のテストを追加。

## 変更ファイル一覧

- `config/source_accounts/default_sources.json`
- `config/source_accounts/production_sources.example.json`
- `scripts/cut_video_clips.py`
- `scripts/import_posted_results.py`
- `scripts/publish_threads_post.py`
- `scripts/publish_x_post.py`
- `scripts/review_source_candidates.py`
- `scripts/run_real_smoke_plan.py`
- `scripts/test_phase13_smoke_plan.py`
- `src/orchestrators/source_to_post_orchestrator.py`
- `src/publishers/threads_publisher.py`
- `src/reference/fetchers/fetcher_registry.py`
- `src/reference/source_registry.py`
- `src/storage/pipeline_store.py`
- `docs/ai-work-handoff.md`
- `docs/phase13-16-test-matrix.md`

## 追加ファイル一覧

- `docs/ai-dev-status.md`
- `docs/codex-final-audit-report.md`
- `docs/media-asset-storage.md`
- `docs/video-clip-execution.md`
- `scripts/download_media_assets.py`
- `scripts/preflight_media_assets.py`
- `scripts/upload_media_assets.py`
- `scripts/test_phase13_article_source_support.py`
- `scripts/test_phase13_fetcher_production_paths.py`
- `scripts/test_phase13_generation_production.py`
- `scripts/test_phase13_media_asset_storage.py`
- `scripts/test_phase13_media_post_preflight.py`
- `scripts/test_phase13_pdca_production_loop.py`
- `scripts/test_phase13_production_sources_real_urls.py`
- `scripts/test_phase13_publishers_production_safety.py`
- `scripts/test_phase13_query_source_support.py`
- `scripts/test_phase13_real_smoke_plan.py`
- `scripts/test_phase13_source_concept_matching.py`
- `scripts/test_phase13_source_fetcher_tool_doctor.py`
- `scripts/test_phase13_source_lifecycle.py`
- `scripts/test_phase13_source_registry_production.py`
- `scripts/test_phase13_source_to_post_production_path.py`
- `scripts/test_phase13_video_clip_execution.py`
- `src/media/cloudinary_uploader.py`
- `src/media/image_asset_pipeline.py`
- `src/media/media_asset_store.py`
- `src/media/media_downloader.py`
- `src/media/video_asset_pipeline.py`
- `src/video/video_clip_executor.py`

## Source 反映結果

- placeholder handle/url tokens: 残り 0
- user-provided fixed URL: 54 / 54 反映済み
- query source: 37件追加
- `production_sources.example.json`: 91 sources / active 0 / fetch_enabled 0 / validation issues 0
- `default_sources.json`: 8 safe default candidates / active 0 / fetch_enabled 0 / validation issues 0

| Account | Fixed Sources | Query Sources | Total |
|---|---:|---:|---:|
| `night_scout` | 18 | 13 | 31 |
| `liver_manager` | 13 | 11 | 24 |
| `beauty_account` | 23 | 13 | 36 |

## Safety / Scale 方針

- `beauty_account` は `WAITING_REVIEW` / draft-only 固定。READY/POSTED 化禁止。
- `candidate_status=approved` 以外は download/cut/upload 不可。
- `rights_policy=unknown` は `WAITING_REVIEW` で media 利用不可。
- `media_policy=do_not_download` は download 禁止。
- `media_policy=plan_only` は保存/投稿利用禁止。
- `reuse_policy=no_reuse` は media 利用禁止。
- `ALLOW_CLOUDINARY_UPLOAD=true` と `--confirm-upload` なしでは upload 禁止。
- PipelineStore は JSON 保存と Sheets write plan を分離。Sheets API 429 は WARN 扱い。
- 既存 Sheets タブ/列の削除は禁止。
- PDCA は提案だけ。`auto_apply=false`、source priority 自動変更なし。
- query source は `source_platform=query` とし、固定 source の X/Youtube/note 件数に混ざらない。

## テスト結果

- Phase 9-13 regression + added tests: 39 files PASS / 0 FAIL
- Dry-run / BLOCKED command sweep: 35 commands PASS / 0 FAIL
- Phase 13 legacy core total: 148 PASS / 0 FAIL

## Dry-run / BLOCKED 確認結果

- `--fetch` without `--confirm-fetch`: BLOCKED
- `--download` without `--confirm-download`: BLOCKED
- `--cut` without `--confirm-cut`: BLOCKED
- `--upload` without `--confirm-upload`: BLOCKED
- real post without `--confirm-post`: BLOCKED
- Source-to-post mock dry-run: PASS, publish step remains BLOCKED without confirm
- Real smoke plan dry-run: ran readiness check only; environment NOT_READY is acceptable WARN
- `run_real_smoke_plan.py --platform threads`: Threads preflight branch confirmed; no X preflight mix-in

## 実行していないこと

- 実 fetch: 未実行
- 実 download: 未実行
- 実 cut: 未実行
- 実 upload: 未実行
- 実投稿: 未実行
- GitHub Actions: 未実行
- Hermes Agent install: 未実行
- secrets/cookie values: 表示なし

## 残 WARN

- `run_real_smoke_plan.py` は資格情報未設定環境では NOT_READY で非ゼロ終了する。dry-run readiness として許容。
- `BasePublisher` / `BaseFetcher` の抽象メソッドに `NotImplementedError` が残る。設計上の抽象クラス。
- legacy docs/tests に古い `NotImplementedError` 記述が残る。
- X collector API stubs は意図的に実取得不可。今回の production source media path 外。

## 未完了事項

- PR 作成とレビュー。
- 実 source の承認運用設計。
- Sheets 実 test-write は未実行。
- 実 credentials readiness は未確認。
- `beauty_account` の法務/薬機法/医療広告レビュー運用。

## 次に Claude Code が触ってよいファイル

- `docs/codex-final-audit-report.md`
- `docs/ai-dev-status.md`
- `docs/phase13-16-test-matrix.md`
- `src/media/*.py`
- `src/video/video_clip_executor.py`
- `scripts/test_phase13_*.py`

## 次に Codex が触ってよいファイル

- `scripts/preflight_media_assets.py`
- `scripts/download_media_assets.py`
- `scripts/upload_media_assets.py`
- `src/storage/pipeline_store.py`
- `src/orchestrators/source_to_post_orchestrator.py`
- `docs/media-asset-storage.md`
- `docs/video-clip-execution.md`

## 衝突しやすいファイル

- `config/source_accounts/production_sources.example.json`
- `config/source_accounts/default_sources.json`
- `src/orchestrators/source_to_post_orchestrator.py`
- `src/storage/pipeline_store.py`
- `scripts/publish_threads_post.py`
- `scripts/publish_x_post.py`
- `docs/ai-work-handoff.md`

## 触らない方がいいファイル

- `.env` and any credential/cookie files
- `.claude/plans/` untracked local work
- `output/`, `logs/`, generated local artifacts
- GitHub Actions workflows unless explicitly requested
- old repo outside `v2`

## 次AIへの引き継ぎメモ

- 作業開始時は必ず `git fetch origin`, `git status -sb`, `git rev-parse HEAD`, `git rev-parse origin/main` を確認する。
- `production_sources.example.json` は full source list、`default_sources.json` は safe subset。
- `beauty_account` を active/READY/POSTED にしない。
- 実 fetch/download/cut/upload/post を試す場合は、ユーザー確認と confirm flags と環境フラグを全部確認する。
- media/clip は現状 plan/preflight 層。実処理の接続は承認済み source だけに限定する。
- PR 前に `python3 scripts/test_phase13_production_sources_real_urls.py` と dry-run/BLOCKED sweep を再実行する。

## Final Rollout Update

- Date: 2026-06-17
- PR URL: https://github.com/dev-ch-hhuk39/sns-growth-engine/pull/1
- PR title: `Finalize production source/media pipeline`
- Merge前確認: PASS
- Merge前テスト: Phase13 minimum 11 / 11 PASS, Phase9-13 regression 39 / 39 PASS
- Merge前 dry-run / BLOCKED: 22 / 22 PASS
- Merge可否: merge-ready
- Merge結果: PR #1 squash merged
- Production pipeline merge SHA: `759af859a4d70d9ec1105f8d70f1c4ea893f29db`
- main反映後HEAD確認: `759af859a4d70d9ec1105f8d70f1c4ea893f29db`
- main反映後最小テスト: 4 / 4 PASS
- main反映後 dry-run / BLOCKED: 5 / 5 PASS
- 実fetch/download/cut/upload/post: 未実行
- secrets/cookie/token/API key: 表示なし

## Follow-up Docs / Smoke Plan Update

- Branch: `feature/final-rollout-status-docs`
- PR URL: https://github.com/dev-ch-hhuk39/sns-growth-engine/pull/2
- PR #2 head before smoke fix: `182cb01eb02373e3c26c5f6886aaa36df7fad06c`
- PR #2 merge attempt: BLOCKED by GitHub connector approval credits (`out of credits`); main direct push was not attempted.
- Follow-up fix: `run_real_smoke_plan.py --platform threads` now runs Threads preflight instead of X preflight.
- Added test coverage in `scripts/test_phase13_smoke_plan.py`.
- Follow-up test results:
  - `python3 scripts/run_real_smoke_plan.py --account-id liver_manager --platform threads --dry-run`: NOT_READY expected in credential-free env; Threads preflight confirmed; no real API/upload/post.
  - `python3 scripts/test_phase13_smoke_plan.py`: 18 / 18 PASS
  - `python3 scripts/test_phase13_publishers_production_safety.py`: 4 / 4 PASS

## 初回スモーク手順

最終版は `docs/manual-smoke-test-sequence.md` と `docs/production-launch-checklist.md` を参照。

固定順序:

1. tool doctor
2. source registry validate
3. source candidate review
4. mock fetch dry-run
5. source_to_post pipeline mock dry-run
6. media preflight dry-run
7. publisher dry-run
8. posted_results import dry-run
9. PDCA dry-run
10. 人間承認後に confirm-fetch を1sourceだけ
11. confirm-fetch後もdownload/cut/upload/postはしない
12. download/cut/upload/postは別承認
13. 初回1投稿はpublisher dry-runまで
14. 実投稿はさらに別承認

## 次に人間がやること

- PR #1 を確認し、main 反映後は `docs/manual-smoke-test-sequence.md` の順番で初回スモークを実施する。
- 実fetchは1sourceだけを明示承認する。
- 実download/cut/upload/post は別承認まで実行しない。

## Pilot Deploy / Final Audit (2026-06-18)

- 担当AI: Claude Code (Sonnet 4.6)
- PR #2: squash merged to main
- main HEAD: `19b0b77148a38717b996fb6df40066a9f6267df8`
- セキュリティ修正: `pipeline_store.py` stage バリデーション追加 (commit `6bb694b`)
- preflight バグ修正: `scripts/preflight_media_assets.py` IndexError修正
- テスト: Phase10-13 全ファイル 0 FAIL
- dry-run/BLOCKED sweep: 全13チェック PASS/BLOCKED
- pilot smoke: night_scout/x, night_scout/threads, liver_manager/threads → [SMOKE PASS]
- 実fetch/download/cut/upload/post: 未実行
- secrets/cookie表示: なし
- 詳細: `docs/pilot-deploy-report.md`

## SNS実運用開始フェーズ (2026-06-18)

- 担当AI: Claude Code (Sonnet 4.6)
- フェーズ: 初回実運用（認証情報未設定のため READY_WITH_MISSING_CREDENTIALS）

### 実施内容（第1回: 519a48a）

- `.gitignore` に `output/` を追加（パイプライン出力をGit管理外に）
- `scripts/fetch_source_posts.py` に `--source-file` / `--bypass-active-check` フラグを追加
- 実 fetch 実行: `src_ns_yt_cand_009` (@kyaba_camera YouTube) から6件取得
- 取得データ: `output/pipeline_runs/fetch_ns_20260618.json`（Git管理外）
- 投稿テキスト生成（確定版99字、スカウト視点、夜職女性向け）
- preflight dry-run: PASS (sources=31, assets=2)
- X publisher dry-run: DRY_RUN ✅ (99字)
- Threads publisher dry-run: DRY_RUN ✅ (99字、1行WARN=問題なし)
- posted_results import dry-run: DRY_RUN ✅
- PDCA dry-run: pdca_8bcc26d2 (suggestions=WAITING_REVIEW, auto_apply=false)
- 安全フラグ全て NOT_SET 確認済み

### 確定投稿テキスト（99字）

```
夜職で伸びる子に共通するのは、LINEの返し方が上手いこと。"また話したい"と思わせる会話ができる子は強い。学歴や見た目より、長く稼ぐには会話力が大事なんだよね。磨ける力だから、今からでも伸ばせる。
```

### 実行していないこと

- 実投稿: 未実行（X/Threads 認証情報が .env に未設定）
- 実download/cut/upload: 未実行
- beauty_account active化: なし
- secrets/cookie表示: なし

### 詳細

- `docs/first-live-post-report.md`（今回新規作成・更新）
- `docs/pdca-live-loop-report.md`（今回新規作成）

## 次に人間がやること

1. `.env` に X または Threads 認証情報を設定する
   - X: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`
   - Threads: `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`
2. `python3 scripts/publish_x_post.py --account-id night_scout --confirm-post --dry-run` で再確認
3. `ALLOW_REAL_X_POST=true`（または `ALLOW_REAL_THREADS_POST=true`）を `.env` に追加（永続コミット禁止）
4. 初回実投稿を実行（text-only、1件のみ）
5. 投稿後 posted_results に登録
6. 24時間後にエンゲージメントを確認し PDCA を実データで再実行

## 次にAIが触ってよいファイル

- `docs/manual-smoke-test-sequence.md`
- `docs/production-launch-checklist.md`
- `docs/first-live-post-report.md`
- `docs/pdca-live-loop-report.md`
- `docs/phase13-16-test-matrix.md`

## 触らない方がいいファイル

- `.env`
- cookie/token/API key を含むファイル
- `.claude/plans/`
- old repo / old zip retreat folders
- 実メディアファイル
