# AI Work Handoff

Codex / Claude Code 並行開発用の引き継ぎ資料です。主要作業完了時は必ず更新してください。

## 最終更新

- Date: 2026-06-24
- 作業AI: Claude Code (Sonnet 4.6)
- 作業ディレクトリ: `/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2`
- GitHub repo: `dev-ch-hhuk39/sns-growth-engine`
- 前回更新: 2026-06-23 (Threads初回実投稿成功 / バグ修正3件)

## 最新作業内容 (2026-06-24)

### X API Legacy 互換方式への移行 + エラー再分類

- `src/publishers/x_publisher.py`: `tweepy.Client` → `requests_oauthlib.OAuth1` (HMAC-SHA1) に変更
  - `TWEET_URL` 定数追加
  - `_handle_post_error()` 追加: 402 CreditsDepleted / 401 / 403 / 429 を個別コードに分類
- **原因**: X API Credits 枯渇（月次クレジット）。旧repo の高頻度 API 呼び出しで消費しきった
- `data/manual_post_queue.json`: 次回実投稿候補テキストを `retry_ready` で保存済み
- `docs/x-api-legacy-compatibility-audit.md`: 新規作成（旧/新 repo 比較・結論・復旧手順）

### Source Registry 拡充 (8 → 17 sources)

- `config/source_accounts/default_sources.json`: 17ソースに更新
  - YouTube 2件 (ns/lm): `rights_policy=reference_only`, `review_notes="ユーザー確認済み (2026-06-24)"`
  - beauty_account 3件: `review_status=BLOCKED_BEAUTY_ACCOUNT`, `active=false`
  - 旧repo移行 X sources 10件: ns 8件 + lm 2件
- `scripts/test_source_rights_user_confirmed.py`: 19項目 全PASS

### Threads 次投稿候補 Queue 保存

- `data/threads_night_scout_next_queue.json`: 3候補 `WAITING_REVIEW` で保存
- 投稿案: LINEの返しテンポ / 店選びの失敗 / 辞めずに続けられる子
- `scripts/test_reference_transform_guard.py`: 22項目 全PASS

### GitHub Actions Workflow 整備

- `.github/workflows/content-daily-dry-run.yml`: X/Threads secrets env 追加
- `.github/workflows/media-approved-pilot.yml`: 新規作成（3モード / 全安全フラグ false）
  - `${{ github.event.inputs.* }}` 直接展開なし（コマンドインジェクション対策）
- `docs/media-approved-pilot.md`: 新規作成

### テスト追加 (5本)

| テスト | PASS | FAIL |
|---|---|---|
| test_x_legacy_compatibility.py | 13 | 0 |
| test_source_rights_user_confirmed.py | 19 | 0 |
| test_cloudinary_upload_guard.py | 9 | 0 |
| test_media_approved_pilot_workflow.py | 13 | 0 |
| test_reference_transform_guard.py | 22 | 0 |

## 現在のブロッカー / ペンディング事項

| 課題 | 内容 | 必要な対応 |
|---|---|---|
| X API Credits 枯渇 | 402 CreditsDepleted。認証は成功済み。tweepy は廃止 | X Developer Portal > Usage & Credits で補充 |
| src_ns_query_001 | query source の URL 未登録 | 対象アカウント URL を入力後 default_sources.json を更新 |
| src_ns_yt_cand_001 / src_lm_yt_cand_001 | rights_policy=reference_only (download 禁止) | approved_media 昇格は別途承認フロー必要 |
| Threads 次投稿 | WAITING_REVIEW の 3候補あり | ユーザーレビュー後に投稿実行 |
| beauty_account | 実投稿・active化禁止 | 永続的な制約 |
| Threads 48h 指標 | 初回投稿の impressions/likes 未取得 | 2026-06-25 以降に Threads インサイトで確認 |

## 最新作業内容 (2026-06-23)

### Threads 初回実投稿 SUCCESS

- アカウント: night_scout (`@kyaba_consul_mizu`)
- 投稿文: 「キャバで指名が取れる子って〜」(86字)
- post_id: `18127402414723102`
- posted_url: https://www.threads.com/@kyaba_consul_mizu/post/DZ6Drm5k9SL
- posted_at: 2026-06-23T00:00:00Z
- posted_results: result_id=`r-5da1d941` (Sheets書き込み済み)
- metrics_status: PENDING (48h後に確認)

### バグ修正 3件

1. **GitHub Actions workflow env渡し漏れ**: `content-pilot-publish.yml` にアカウント固有 Threads secrets 8本を追加。`THREADS_ACCESS_TOKEN_NIGHT_SCOUT` 等が workflow から参照可能に。
2. **Threads post_url 生成方法**: 数値 user_id URL（無効）→ Threads API permalink 取得 (`_try_fetch_permalink`)。
3. **PublishResult.is_dry_run_ok @property**: デコレータ欠落 → bound method が常に truthy → 実投稿時も "DRY_RUN" 表示。`@property` 追加で修正。

### Source registry 整備

- `docs/youtube-tiktok-clipping-runbook.md`: 新規作成（clip pipeline 実行手順・前提条件・制約一覧）
- 全 8ソースの状態を確認・更新

### テスト追加

| テスト | PASS | FAIL |
|---|---|---|
| test_content_workflows_safety.py (更新: +1件) | 8 | 0 |
| is_dry_run_ok @property 確認 (新規) | 1 | 0 |

## 現在のブロッカー / ペンディング事項

| 課題 | 内容 | 必要な対応 |
|---|---|---|
| X API 402 | APIクレジット不足。認証は成功済み | X Developer Portal で Basic Plan 以上を契約 |
| src_ns_query_001 | night_scout query source の URL 未登録 | 対象アカウント URL を入力後 default_sources.json を更新 |
| src_ns_yt_cand_001 / src_lm_yt_cand_001 | rights_policy=unknown | YouTube チャンネルの利用規約を確認し権利ポリシーを更新 |
| content_categories 空 | WARN (機能影響なし) | setup_and_verify.py --setup で解消可能 |
| beauty_account | 実投稿・active化禁止 | 永続的な制約 |
| Threads 48h 指標 | impressions/likes/replies 未取得 | 2026-06-25 以降に Threads インサイトで確認 |

## 最新作業内容 (2026-06-22 第2回)

### X API ブロッカー分離

- `src/publishers/x_publisher.py`: `_is_billing_error()` + `_save_to_manual_queue()` 追加
  - 402 を `POST_FAILED_EXTERNAL_BILLING_BLOCKER` として認証エラーと区別
  - 失敗投稿文を `data/manual_post_queue.json` に退避
- `data/manual_post_queue.json`: 2026-06-22 の X 失敗投稿文を `retry_ready` で保存
- `docs/x-api-billing-blocker.md`: 復旧手順・エラーコード定義を記載

### Threads 実投稿確認

- dry-run: **PASS** (85字、account=night_scout)
- 実投稿: **BLOCKED_MISSING_CREDENTIALS** — THREADS_ACCESS_TOKEN / THREADS_USER_ID が .env 未設定

### Source registry 棚卸し

- 全 8件の状態を確認・整理（READY_FOR_REFERENCE_FETCH / WAITING_RIGHTS_REVIEW / BLOCKED_BEAUTY_ACCOUNT）
- `docs/source-intake-template.md`: 新規ソース登録手順・状態定義表を作成
- `scripts/test_source_intake_schema.py`: 7項目テスト（全PASS）

### Media policy guard 確認

- `check_source_media_policy()` / Cloudinary upload guard の動作を確認
- `scripts/test_media_policy_guard.py`: 8項目テスト（全PASS）

### GitHub Actions workflows 追加（本番ON はまだしない）

- `.github/workflows/content-daily-dry-run.yml`: 毎日 JST 10:00 dry-run サニティチェック
- `.github/workflows/content-pilot-publish.yml`: 手動トリガー専用 / X 402 自動停止 / beauty_account ガード
- `.github/workflows/source-fetch-dry-run.yml`: 毎週月曜 JST 11:00 source policy チェック
- 全 workflow: `${{ inputs.* }}` を env 経由に限定（コマンドインジェクション対策）
- `scripts/test_content_workflows_safety.py`: 7項目テスト（全PASS）

### テスト結果（今回追加分）

| テスト | PASS | FAIL |
|---|---|---|
| test_source_intake_schema.py | 7 | 0 |
| test_media_policy_guard.py | 8 | 0 |
| test_content_workflows_safety.py | 7 | 0 |
| test_account_tone_guide.py（既存） | 41 | 0 |

## 現在のブロッカー / ペンディング事項

| 課題 | 内容 | 必要な対応 |
|---|---|---|
| X API 402 | APIクレジット不足。認証は成功済み | X Developer Portal で Basic Plan 以上を契約 |
| Threads 実投稿 | THREADS_ACCESS_TOKEN / THREADS_USER_ID が .env 未設定 | .env に認証情報を追加 |
| src_ns_query_001 | night_scout query source の URL 未登録 | 対象アカウント URL を入力後 default_sources.json を更新 |
| content_categories 空 | WARN (機能影響なし) | setup_and_verify.py --setup で解消可能 |
| beauty_account | 実投稿・active化禁止 | 永続的な制約 |

## 最新作業内容 (2026-06-22)

### トンマナ強制対応

- `src/seeds.py`: night_scout/liver_manager の tone/notes 詳細化、NGトーンリスト追加
- `src/seeds.py`: `_DRAFT_GEN_NIGHT_SCOUT` / `_DRAFT_GEN_LIVER_MANAGER` 書き直し（スタイルガイド・良い例追加）
- `src/seeds.py`: `_SOCIAL_DERIVATIVE_X_NIGHT_SCOUT` (pt_06) night_scout専用Xテンプレート追加
- `src/seeds.py`: `ACCOUNT_NG_TONE_PATTERNS` 追加（night_scout:21件、liver_manager:12件）
- `src/tone_checker.py`: 新規作成（`check_ng_tone()` 関数）
- `src/prompt_loader.py`: `get_derivative_template()` account_id対応
- `src/social_derivative_generator.py`: account_id を derivative テンプレート選択に渡す
- `scripts/preflight_check.py`: グループ6「トンマナ確認」追加、タブ存在確認を日本語名対応
- `scripts/test_account_tone_guide.py`: 新規作成（41項目全PASS）
- `docs/account-tone-guides.md`: 新規作成

### 初回パイロット実行（X投稿試行）

- 投稿文: 「指名が取れるキャバ嬢は、見た目だけじゃなく〜稼げる子の秘密なんだよね。」(81字)
- dry-run: PASS
- 実投稿: **POST_FAILED** — `402 Payment Required` (認証成功、APIクレジット不足)
- 二重投稿リスクなし（post_id未払い出し）

### コード修正（バグフィックス）

- `scripts/publish_x_post.py`: `sys.path` に `src/` を追加 + dotenv ロード追加
- `scripts/publish_threads_post.py`: 同様の修正
- `scripts/preflight_check.py`: `check_tabs_existence()` で `TAB_DISPLAY_NAMES` を使い日本語タブ名に対応

### テスト結果

- test_account_tone_guide.py: 41 PASS / 0 FAIL
- test_consolidation_phase.py: 22 PASS / 0 FAIL
- test_phase13_publishers_production_safety.py: 4 PASS / 0 FAIL
- test_phase13_smoke_plan.py: 18 PASS / 0 FAIL
- test_threads_credentials.py: 24 PASS / 0 FAIL
- check_credentials_readiness.py: READY (必須20件全設定済み)

## 現在のブロッカー

| 課題 | 内容 | 対応 |
|---|---|---|
| X API クレジット不足 | 402 Payment Required — Basic Plan相当のクレジットが必要 | X Developer Portal で有料プランを確認 |
| content_categories 空 | WARN (機能影響なし) | setup_and_verify.py --setup で解消可能（Sheets API 429に注意） |
| prompt_templates 空 | WARN (機能影響なし) | 同上 |

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

## 運用統合フェーズ (2026-06-20)

- 担当AI: Claude Code (Sonnet 4.6)
- フェーズ: 旧3リポジトリ → sns-growth-engine 一本化

### 実施内容

- `docs/legacy-repo-migration-audit.md`: 旧3repo の詳細調査結果を作成
- `docs/legacy-repo-shutdown-plan.md`: 旧 repo 停止手順を作成
- `docs/credential-migration-plan.md`: 認証情報移行計画を作成
- `docs/production-launch-checklist.md`: 統合ポリシーセクションを追加
- `src/sheets_client.py`: TAB_DISPLAY_NAMES（日本語タブ名）マッピング追加（Task F）
- `scripts/migrate_sheet_tabs_to_japanese.py`: シートタブ移行 CLI 追加（Task F）
- `scripts/refresh_threads_token.py`: Threads トークンリフレッシュスクリプト追加（Task G）
- `src/publishers/threads_publisher.py`: Phase 3-E 実投稿実装（Task G）
- `.env.template`: アカウント別 Threads 変数・トークン保存先を追加（Task H）
- テスト追加（Task I）

### 旧リポジトリ状況

| リポジトリ | 投稿頻度 | 状況 |
|---|---|---|
| X_autopost_yoru | 6回/日 (night_scout/X) | **未停止** — 人間による GitHub Actions disable が必要 |
| threads_auto_post_gs | 2回/日 (night_scout/Threads) | **未停止** — 同上 |
| threads-liver-coachhing | 8回/日 (liver_manager/Threads) | **未停止** — 同上（最優先） |

**新 repo での本番投稿前に、旧 repo の全 workflow を disable すること。**

### 実行していないこと

- 旧 repo の削除・archive（人間が判断・実施）
- 旧 repo の GitHub Actions disable（人間が GitHub UI で実施）
- secret 値の確認・コピー（実施しない）
- 実投稿（認証情報設定後に人間が承認して実施）

### 次に人間がやること（統合フェーズ）

1. **旧 repo 停止（最優先）**
   - `docs/legacy-repo-shutdown-plan.md` 参照
   - threads-liver-coachhing → X_autopost_yoru → threads_auto_post_gs の順で disable
2. **認証情報設定**
   - `docs/credential-migration-plan.md` 参照
   - `.env` に `THREADS_ACCESS_TOKEN_NIGHT_SCOUT` / `THREADS_USER_ID_NIGHT_SCOUT`
   - `.env` に `THREADS_ACCESS_TOKEN_LIVER_MANAGER` / `THREADS_USER_ID_LIVER_MANAGER`
   - `SNS_MASTER_SHEET_ID` を設定
3. **Threads publisher Phase 3-E 動作確認**
   - `scripts/refresh_threads_token.py --account-id night_scout --confirm-refresh --dry-run`
   - `scripts/publish_threads_post.py --account-id night_scout --dry-run`
4. **本番投稿（1件ずつ承認制）**
   - X: `docs/first-live-post-report.md` の確定テキストで実行
   - Threads: 同様に 1件ずつ

## 次にAIが触ってよいファイル（統合フェーズ以降）

- `docs/legacy-repo-migration-audit.md`
- `docs/legacy-repo-shutdown-plan.md`
- `docs/credential-migration-plan.md`
- `docs/production-launch-checklist.md`
- `src/sheets_client.py` (TAB_DISPLAY_NAMES 追加のみ)
- `src/publishers/threads_publisher.py` (Phase 3-E 実装)
- `scripts/refresh_threads_token.py` (新規追加)
- `scripts/migrate_sheet_tabs_to_japanese.py` (新規追加)
- `.env.template` (アカウント別変数追加)

## 触らない方がいいファイル（統合フェーズ以降）

- `.env`
- 旧 repo の任意ファイル（docs/legacy-repo-migration-audit.md を参照のみ）
- `config/source_accounts/production_sources.example.json`（active/fetch_enabled は false のまま）
- `config/accounts/*.json`（beauty_account は draft_only のまま）
- 実メディアファイル
