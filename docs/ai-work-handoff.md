# AI Work Handoff

Codex / Claude Code 並行開発用の引き継ぎ資料です。主要作業完了時は必ず更新してください。

## 最終更新

- Date: 2026-06-29
- 作業AI: Claude Code (Opus 4.8)
- 作業ディレクトリ: `/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2`
- GitHub repo: `dev-ch-hhuk39/sns-growth-engine`
- 前回更新: 2026-06-24 (Threads初回実投稿成功 / バグ修正3件 ほか)

## 最新作業内容 (2026-06-29) — Threads worker READY 承認モデル必須化（Phase 3）

**重要（現行仕様）**: Threads worker が投稿するのは **`status=READY` の行のみ**（`process_threads_queue.py` `ELIGIBLE_STATUSES = {"READY"}`）。
本ドキュメント下部の旧エントリにある「`WAITING_REVIEW` / `PLANNED` のみ対象」は **旧仕様** であり、以後は無効。

- 投稿可否モデル: `WAITING_REVIEW → READY → PROCESSING → POSTED`。
  - `WAITING_REVIEW`: 生成系CLIの既定出力（レビュー待ち、投稿不可）
  - `DRAFT`: 生成 / PDCA 候補（投稿不可）
  - `PLANNED`: 計画段階（投稿不可）
  - `READY`: 人間が `approve_queue.py` で承認済み（worker 投稿対象）
  - `POSTED`: 投稿完了（再投稿しない）
- `READY` 昇格は **`approve_queue.py`（WAITING_REVIEW → READY/REJECTED）経由のみ**。生成系CLIは `READY` を直接書かない。承認時 logs に `queue_approved` 証跡。
- X 側 `publish_queue.py`（`--status READY` 必須）と対称化。旧「承認モデル非対称」課題は解消。
- verify（`recover_production_sheets_threads_first.py`）に READY 承認モデル安全チェック10件追加。check 総数 51 件、合格条件 `failed=[]`。
  - `generated_candidates_not_ready_by_default` は logs の `queue_approved` 証跡で人間承認済み生成行を誤検知しない。
  - media 権利チェックは `media_url` / `media_asset_id` 双方で連携。
- 回帰固定テスト `test_recover_verify_ready_checks.py` ほか READY 系を追加。offline curated suite **55 / 55 PASS**。
- 更新docs: `threads-queue-worker.md` / `threads-operation-runbook.md` / `sheets-manual-check-guide.md` / `reference-pipeline-runbook.md` / `production-completion-status.md` / 本ファイル。
- 安全境界（変更なし）: 実投稿/実upload/download なし。`PUBLISH_ENABLED` / `ALLOW_REAL_THREADS_POST` / `ALLOW_CLOUDINARY_UPLOAD` 等は false 既定。beauty_account は draft_only。X は将来実装予定（設計・docs から削除しない）。

## 最新作業内容 (2026-06-24)

### Codex: Threads Queue Worker / Metrics Import Loop 実装

- 作業AI: Codex
- 作業ブランチ: `main`
- 作業開始HEAD: `5e4197eba17c25730d59b400df0113a5ef381169`
- 現在HEAD: このhandoffを含む最新commit。最終hashは `git rev-parse HEAD` / 完了報告で確認。
- origin/main開始確認: `5e4197eba17c25730d59b400df0113a5ef381169`
- 作業ディレクトリ: `/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2`
- 目的: Sheets `投稿キュー` から Threads 投稿を1件ずつ安全に処理し、posted_results / queue / logs / PDCA まで接続する。

#### 本システムについて

- `night_scout` / `liver_manager` は Threads-first 運用。
- `beauty_account` は `draft_only` / CTAなし / 実投稿禁止。
- X投稿は当面OFF。X queueも作らない。
- media download / cut / upload / Cloudinary upload / transcription API は未実行・無効。
- `learning_rules.active=false`、`auto_apply=false` を維持し、PDCA提案は `WAITING_REVIEW` に留める。

#### 変更ファイル一覧

- `.github/workflows/content-daily-dry-run.yml`
- `.github/workflows/threads-queue-worker.yml`
- `src/config_loader.py`
- `src/sheets_client.py`
- `scripts/recover_production_sheets_threads_first.py`
- `scripts/process_threads_queue.py`
- `scripts/import_threads_metrics_manual.py`
- `scripts/refill_threads_queue.py`
- `scripts/test_process_threads_queue.py`
- `scripts/test_threads_queue_duplicate_guard.py`
- `scripts/test_posted_results_integrity.py`
- `scripts/test_import_threads_metrics_manual.py`
- `scripts/test_refill_threads_queue.py`
- `scripts/test_threads_queue_worker_workflow.py`
- `scripts/test_content_workflows_safety.py`
- `scripts/test_x_disabled_mode.py`
- `scripts/test_beauty_account_block.py`
- `docs/threads-queue-worker.md`
- `docs/metrics-import-runbook.md`
- `docs/threads-operation-runbook.md`
- `docs/sheets-manual-check-guide.md`
- `docs/production-completion-status.md`
- `docs/production-launch-checklist.md`
- `docs/ai-dev-status.md`
- `docs/phase13-16-test-matrix.md`
- `docs/ai-work-handoff.md`

#### 追加ファイル一覧

- `.github/workflows/threads-queue-worker.yml`
- `scripts/process_threads_queue.py`
- `scripts/import_threads_metrics_manual.py`
- `scripts/refill_threads_queue.py`
- `scripts/test_process_threads_queue.py`
- `scripts/test_threads_queue_duplicate_guard.py`
- `scripts/test_posted_results_integrity.py`
- `scripts/test_import_threads_metrics_manual.py`
- `scripts/test_refill_threads_queue.py`
- `scripts/test_threads_queue_worker_workflow.py`
- `docs/threads-queue-worker.md`
- `docs/metrics-import-runbook.md`

#### 実装内容

- `process_threads_queue.py`
  - （※旧仕様。現在は worker 投稿対象は `READY` のみ。冒頭の 2026-06-29 エントリ参照）`WAITING_REVIEW` / `PLANNED` の Threads queue row のみ対象。
  - `beauty_account` BLOCKED、X row ignored。
  - dry-runは投稿なしで候補・validation結果を出力。
  - real modeは `PUBLISH_ENABLED=true` + `ALLOW_REAL_THREADS_POST=true` + `--confirm-real-post` 必須。
  - duplicate guard: `queue_id` / `derivative_id` / `draft_id` / same text-account-platform。
  - 成功時: queue `POSTED`、posted_results `POSTED/PENDING`、logs、PDCA initial、suggestion `WAITING_REVIEW`。
  - 投稿失敗時: queue `FAILED`、即retryなし。
  - posted_results保存失敗時: queue `POSTED_SAVE_FAILED`、`output/posted_results_fallback/*.json` 退避、再投稿禁止。
- `import_threads_metrics_manual.py`
  - 手入力Threads metricsを `posted_results` に反映。
  - `metrics_status=MEASURED`、logs / pdca_runs / suggestions を作成。
- `refill_threads_queue.py`
  - `night_scout` / `liver_manager` のThreads投稿案を `drafts` / `social_derivatives` / `queue` に補充。
  - `beauty_account` とXは作成しない。
- GitHub Actions
  - `threads-queue-worker.yml`: `workflow_dispatch` only。scheduleなし。dry-run後にだけ処理。
  - `content-daily-dry-run.yml`: Threads-first dry-runへ変更。
- Sheets
  - `posted_results` に queue/derivative/platform/external id/metrics/status/text/source columns を追加。
  - `SheetsClient._ws()` に worksheet cache を追加し、setup/workerのSheets read quotaを削減。
- verify
  - `recover_production_sheets_threads_first.py` の `verify_state()` を posted_results整合性、metrics_status、queue整合、duplicate textまで厳密化。

#### 未完了事項

- Live Sheets上での厳密30チェック verify-only は未完了。
- Live Sheets上での `process_threads_queue.py --account-id night_scout --dry-run` / `liver_manager --dry-run` は未完了。
- Live Sheets上での `refill_threads_queue.py --dry-run` は未完了。
- 理由: Google Sheets実行のための承認システムが `out of credits` で rejected。迂回はしていない。
- 実投稿は今回未実行。

#### 残WARN

- Sheets API 429 が発生した後、`posted_results` の新規列追加までは完了。backfill/strict verify は承認credits復旧後に再実行すること。
- `check_credentials_readiness.py`: Cloudflare transcription任意credential、GitHub secret write token は optional missing。必須20件はREADY。
- X credentialsはSETだが、X投稿運用は引き続きOFF。

#### 全テスト結果

- `test_account_tone_guide.py`: PASS 41 / FAIL 0
- `test_threads_credentials.py`: PASS 24 / FAIL 0
- `test_phase13_publishers_production_safety.py`: PASS 4 / FAIL 0
- `test_content_workflows_safety.py`: PASS 9 / FAIL 0
- `test_source_intake_schema.py`: PASS 7 / FAIL 0
- `test_media_policy_guard.py`: PASS 8 / FAIL 0
- `test_sheets_seed_state.py`: PASS 7 / FAIL 0
- `test_cta_rules.py`: PASS 6 / FAIL 0
- `test_threads_queue_seed.py`: PASS 6 / FAIL 0
- `test_beauty_account_block.py`: PASS 9 / FAIL 0
- `test_x_disabled_mode.py`: PASS 9 / FAIL 0
- `test_process_threads_queue.py`: PASS 8 / FAIL 0
- `test_threads_queue_duplicate_guard.py`: PASS 5 / FAIL 0
- `test_posted_results_integrity.py`: PASS 7 / FAIL 0
- `test_import_threads_metrics_manual.py`: PASS 4 / FAIL 0
- `test_refill_threads_queue.py`: PASS 8 / FAIL 0
- `test_threads_queue_worker_workflow.py`: PASS 11 / FAIL 0
- `check_credentials_readiness.py`: READY for required 20 items; optional WARN only.

#### dry-run結果

- ローカル・credential不要dry-run:
  - `import_threads_metrics_manual.py --dry-run`: PASS。
- Live Sheets dry-run:
  - 未完了。承認システム `out of credits` によりGoogle Sheetsアクセス不可。

#### confirmなしBLOCKED確認結果

- `test_phase13_publishers_production_safety.py`: confirmなしX post BLOCKED、beauty BLOCKED、publisher dry-run PASS。
- `process_threads_queue.py`: real mode は `--confirm-real-post` なしでBLOCKED、さらに `PUBLISH_ENABLED` / `ALLOW_REAL_THREADS_POST` なしでBLOCKED。
- 実fetch / 実download / 実cut / 実upload / 実post は今回未実行。

#### 次にClaude Codeが触ってよいファイル

- `scripts/process_threads_queue.py`
- `scripts/import_threads_metrics_manual.py`
- `scripts/refill_threads_queue.py`
- `docs/threads-queue-worker.md`
- `docs/metrics-import-runbook.md`
- `docs/threads-operation-runbook.md`
- `docs/sheets-manual-check-guide.md`

#### 次にCodexが触ってよいファイル

- `scripts/recover_production_sheets_threads_first.py`
- `src/sheets_client.py`
- `.github/workflows/threads-queue-worker.yml`
- `.github/workflows/content-daily-dry-run.yml`
- `scripts/test_*threads*queue*.py`

#### 衝突しやすいファイル

- `src/sheets_client.py`
- `scripts/recover_production_sheets_threads_first.py`
- `.github/workflows/content-daily-dry-run.yml`
- `docs/ai-work-handoff.md`
- `docs/production-launch-checklist.md`

#### 触らない方がいいファイル

- `.env`
- `data/threads_tokens/`
- `output/media_cache/`
- `output/cloudinary_cache/`
- `output/posted_results_fallback/` の実運用退避ファイル
- `.claude/plans/`（未追跡のためcommitしない）
- `docs/session-report-2026-06-22-2.md`（未追跡の既存ファイル。今回commit対象外）

#### 次AIへの引き継ぎメモ（2026-06-25更新）

1. **verify は現在 PASS** (`verification_passed=33 failed=0`)。`--verify-only` のみ実行すれば確認できる。
2. `repair_posted_results_integrity.py --apply` は workflow に組み込み済み（毎回 verify 前に自動実行）。
3. `process_threads_queue.py --account-id night_scout --dry-run` → status=DRY_RUN ✓
4. `process_threads_queue.py --account-id liver_manager --dry-run` → status=DUPLICATE_BLOCKED ✓（duplicate guard 正常。liver_manager に新候補が必要なら `refill_threads_queue.py` を実行）
5. 実投稿は原則まだしない。dry-run PASS後、1アカウント1件だけ `PUBLISH_ENABLED=true ALLOW_REAL_THREADS_POST=true --confirm-real-post --max-posts 1`。
6. `POSTED_SAVE_FAILED` が出た場合は絶対に再投稿しない。fallback JSONと実SNS画面を照合してposted_resultsを手で復旧する。
7. `beauty_account`、X、media download/cut/upload、Cloudinary upload、transcription APIは引き続きOFF。

### Codex: true dry-run / Actions dry_run follow-up (2026-06-25)

- 作業開始HEAD: `b3f6188296424c0b74f22b92adeaa65619abc47d`
- code/test commit: `97950f75e272c47f94a8bc78c7f94ef09fa2a28f`
- workflow secret fallback commit: `3b862de49b6441ec8bd8ef6ed8820b9ab108dd55`
- true dry-run修正:
  - `process_threads_queue.py --dry-run`: `setup_all()`なし、read-only出力あり。
  - `refill_threads_queue.py --dry-run`: `setup_all()`なし、appendなし、planned/tone_check出力あり。
  - `import_threads_metrics_manual.py --dry-run`: Sheets接続なし。実行時も不要な `setup_all()` を削除。
- Live local Sheets verify:
  - `python3 scripts/recover_production_sheets_threads_first.py --verify-only --json` は承認システム `out of credits` で拒否。迂回せず未実行。
- GitHub Actions dry_run:
  - run `28136692522`: failure。Sheets secrets未設定で `SNS_MASTER_SHEET_ID` missing。
  - run `28136764181`: failure。fallback追加後もrepositoryにSheets secretsがなく、verify前に停止。
  - `gh secret list` でThreads secretsは確認、Sheets secretsは未登録。
  - `gh secret set` はGitHub API接続エラーで登録未完了。値は表示していない。
- 実投稿: 未実行。
- metrics import:
  - dummy `--dry-run` 実行PASS。
- 追加テスト:
  - `test_true_dry_run_no_setup_all.py`: PASS 7 / FAIL 0
  - `test_live_verify_schema_strictness.py`: PASS 10 / FAIL 0
  - `test_metrics_import_dry_run_no_sheets_connection.py`: PASS 3 / FAIL 0
- 次に必要:
  1. GitHub repository secretsへ `SNS_MASTER_SHEET_ID` または `SPREADSHEET_ID` を登録。
  2. `SA_JSON_BASE64` または `GCP_SA_JSON_BASE64` を登録。
  3. GitHub UIで `Threads Queue Worker` を `dry_run` / `night_scout` / `max_posts=1` / `confirm=false` で実行。
  4. PASS後にLive local Sheets dry-runを再確認。

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

### Sheets 429 対策・孤児投稿復旧 (2026-06-25)

- 作業開始HEAD: `93977a5`
- 作業完了HEAD: このcommit。最終 hash は `git rev-parse HEAD` で確認。

#### 問題

GitHub Actions `threads-queue-worker.yml` real_post 実行後、Threads 投稿は成功したが
Sheets API 429 で `save_posted_result()` / `update_row()` が両方失敗し:
- `recovery_night_scout_queue_01` が PROCESSING に残存
- `posted_results` に行未追加（孤児投稿状態）

#### 修正内容

1. `process_threads_queue.py`
   - `_headers_cache` + `_get_headers()`: ヘッダー行キャッシュ（同一 ws は 1 回のみ `row_values(1)`）
   - `_get_headers()` に 429 指数バックオフ（5s/15s/30s、最大 4 回）
   - real_post モードの `client.setup_all()` を削除
   - `FALLBACK_DIR` 定数追加、`write_fallback()` に `dry_run` パラメータ追加

2. `scripts/recover_orphan_threads_post.py` 新規作成
   - Threads API でテキスト一致探索、またはIDを直接指定して RECOVERED 行追加
   - `--skip-api-lookup` で API なしでも復旧可能
   - 実行済み: `recovery_night_scout_queue_01` → POSTED、posted_results に RECOVERED 行追加

3. `.github/workflows/threads-queue-worker.yml`
   - `output/posted_results_fallback/` を `actions/upload-artifact` で 30 日保存 (`if: always()`)

4. `recover_production_sheets_threads_first.py`
   - `queue_night_scout_3` → `queue_night_scout_2`（孤児復旧で active 行が 2 に）

5. テスト 4 本追加（全 PASS）:
   - `test_recover_orphan_threads_post.py`: 13 PASS
   - `test_sheets_rate_limit_backoff.py`: 14 PASS
   - `test_queue_worker_no_setup_all_in_real_mode.py`: 12 PASS
   - `test_fallback_artifact_no_secrets.py`: 11 PASS

#### 確認結果

```
verification_passed=33 failed=0
count_posted_results=4
count_queue_night_scout=2
```

- `process_threads_queue.py --account-id night_scout --dry-run`: queue_02 status=DRY_RUN ✓
- `process_threads_queue.py --account-id liver_manager --dry-run`: status=DUPLICATE_BLOCKED ✓

#### 次AIへの引き継ぎメモ

1. **孤児投稿 external_post_id**: `recovery_night_scout_queue_01` の posted_result (`orphan_recovery_recovery_night_scout_queue_01_*`) は `external_post_id=""` のまま。Threads アプリで実際の投稿URLを確認し、`recover_orphan_threads_post.py --apply --external-post-id <id>` で更新すること。
2. **verify は PASS 維持**: `verification_passed=33 failed=0`。毎回 repair → verify の手順。
3. **次投稿**: `night_scout` には WAITING_REVIEW (queue_02) / PLANNED (queue_03) が 2 件残存。レビュー後に 1 件ずつ実行。
4. **429 対策は実装済み**: 次回実投稿時は `setup_all` 呼び出しなし・ヘッダーキャッシュ・バックオフ付き。
5. **fallback artifact**: 次回実投稿失敗時は GitHub Actions > Artifacts > `threads-post-fallback-{run_id}` を確認。

## 現在のブロッカー / ペンディング事項

| 課題 | 内容 | 必要な対応 |
|---|---|---|
| X API Credits 枯渇 | 402 CreditsDepleted。認証は成功済み。tweepy は廃止 | X Developer Portal > Usage & Credits で補充 |
| src_ns_query_001 | query source の URL 未登録 | 対象アカウント URL を入力後 default_sources.json を更新 |
| src_ns_yt_cand_001 / src_lm_yt_cand_001 | rights_policy=reference_only (download 禁止) | approved_media 昇格は別途承認フロー必要 |
| Threads 次投稿 | WAITING_REVIEW 2候補あり (night_scout のみ) | ユーザーレビュー後に投稿実行 |
| night_scout 孤児投稿 | external_post_id が空 | Threads アプリで投稿URL確認→ recover_orphan_threads_post.py で更新 |
| beauty_account | 実投稿・active化禁止 | 永続的な制約 |
| Threads 48h 指標 | 初回投稿の impressions/likes 未取得 | Threads インサイトで確認 |

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

## Sheets 実運用リカバリー (2026-06-24)

- 担当AI: Codex
- ブランチ: `main`
- 目的: Google Sheets がほぼ空だった状態から、Threads-first 実運用に必要な初期データを実Sheetsへseedし、read-after-writeで検証。
- 事前push: 未pushだった `b91c26f fix: reconcile x legacy posting and enable media source pipeline` を `origin/main` へpush済み。

### 実施内容

- `scripts/recover_production_sheets_threads_first.py` を追加。
- `src/sheets_client.py` に Threads-first / CTA / source media policy / posted_results 用の不足列を追加。
- `src/seeds.py` のアカウントseedを Threads-first / LINE_AND_DM / beauty CTAなしへ更新。
- Google Sheetsに以下を実書き込み:
  - アカウント管理 3件
  - 投稿カテゴリ 17件
  - プロンプト管理 5件
  - 収集元アカウント 17件
  - 動画収集元 4件
  - 投稿下書き 6件
  - SNS投稿文 6件
  - 投稿キュー night_scout 3件 / liver_manager 3件 / beauty 0件
  - 学習ルール 3件 (`active=false`, `auto_apply=false`)
  - 実行ログ
- `posted_results` に復旧記録と liver_manager 実投稿結果を記録。
- `liver_manager` Threads 実投稿を1件だけ実行。即retryなし。

### Read-after-write結果

- `python3 scripts/recover_production_sheets_threads_first.py --verify-only`
- result: 21 / 21 PASS
- posted_results: 3件
- media_assets: 0件、未承認uploadなし
- X queue: 0件
- Cloudinary upload: 未実行
- download/cut/upload/transcription: 未実行

### テスト結果

- `test_account_tone_guide.py`: PASS 41 / FAIL 0
- `test_threads_credentials.py`: PASS 24 / FAIL 0
- `test_phase13_publishers_production_safety.py`: PASS 4 / FAIL 0
- `test_content_workflows_safety.py`: PASS 8 / FAIL 0
- `test_source_intake_schema.py`: PASS 7 / FAIL 0
- `test_media_policy_guard.py`: PASS 8 / FAIL 0
- 追加テスト5本: PASS
- `check_credentials_readiness.py`: READY、Cloudflare/GH write tokenは任意MISSING

### 残WARN

- Google Sheets API read quota 429 が発生したため、復旧CLIはworksheet cache / batch upsertへ最適化済み。
- X投稿は停止中。X API調査は今回対象外。
- Cloudinary credentialsはSETだが `ALLOW_CLOUDINARY_UPLOAD=false` 維持。
- beauty_account は引き続き draft_only / 実投稿禁止。

### 次AIへのメモ

- Google Sheets確認は `scripts/recover_production_sheets_threads_first.py --verify-only` を使う。
- 実投稿はThreadsのみ、1件ずつ、dry-run後。失敗時の即retryは禁止。
- `data/threads_tokens`, `.env`, `output/media_cache`, `cloudinary_cache` はcommit禁止。

## 過去共有sourceの回収・seed (2026-06-29 追記)

- **ユーザーは過去にソースアカウントURL/選定ルールを共有済み**。「URLを入れてください」と返さない。
- 既存 repo / `production_sources.example.json` から回収し `config/source_accounts/default_sources.json` へ dedup マージ済み(17→59件)。真実源は default_sources.json(`src/reference/source_registry.py` がロード)。
- seed: `python3 scripts/seed_source_registry.py --dry-run --target-account all --platform all`(apply は `--apply --confirm-seed`)。
- 安全方針: **X は今は投稿/開発対象外だが reference source として保持**(active=false/fetch_enabled=false/manual_only)。**TikTok/YouTube は動画参考・文字起こし・切り抜き候補化の対象だが reference_only / can_reuse_media=false**。**beauty は将来用で active=false**(posting account は `beauty_account` 維持、ラベルは `future_track=beauty_future`)。公式メディアは低優先(`low_priority_media_official`)。URL未入力は `WAITING_URL_INPUT`。third-party素材は勝手に再利用しない。
- verify: `recover_production_sheets_threads_first.py --verify-only` に source registry 10 checks 追加。registry を増やした直後は `source_registry_reflected`/`video_sources_reflected` が「Sheets未seed」を示し fail することがある(seed apply で解消)。
- 詳細・追加URL貼り付け形式・次手順(収集→採点→投稿案生成): [source-recovery-and-seed.md](source-recovery-and-seed.md)。

## Codex source registry 統合最終監査 (2026-06-29 追記)

### 現在のHEAD / ブランチ

- 作業ブランチ: `feature/codex-source-registry-integration`
- 作業開始HEAD: `6942179828c5efb55c24e9287f02f7e8c8c1c628`
- origin/main確認: `6942179828c5efb55c24e9287f02f7e8c8c1c628`
- 実装commit: `3dc6e4c4167ee39e193947e2b0f93150849aef58`
- handoff docs commit: `0eaa271258ce0a050c8498f7bc363e61fbeb8438`（この行以降の最終push HEADは `git rev-parse HEAD` / 最終報告を参照）

### 本システムについて

- 真実源は `config/source_accounts/default_sources.json`。`src/reference/source_registry.py` と seed/recovery 経路はこの registry を使う。
- `source_rows()` は `source_accounts` / `reference_sources` タブへ変換する正規化層。Sheets へ書く前に safety field をここで強制する。
- `beauty_account` は posting account id のまま維持する。`beauty_future` は `future_track` / `source_track` / `usage_scope` の label のみ。target に使わない。

### 変更ファイル一覧

- `config/source_accounts/default_sources.json`
- `config/source_accounts/production_sources.example.json`
- `config/source_accounts/recovered_shared_sources.json`
- `scripts/recover_production_sheets_threads_first.py`
- `scripts/seed_source_registry.py`
- `scripts/test_seed_source_registry.py`
- `scripts/test_source_registry_verify_checks.py`
- `src/reference/source_scoring.py`
- `src/sheets_client.py`
- `docs/ai-work-handoff.md`
- `docs/ai-dev-status.md`
- `docs/phase13-16-test-matrix.md`
- `docs/source-recovery-and-seed.md`
- `docs/source-account-registry.md`
- `docs/production-completion-status.md`
- `docs/source-collection-runbook.md`

### 追加ファイル一覧

- `config/source_accounts/recovered_shared_sources.json`
- `scripts/seed_source_registry.py`
- `scripts/test_seed_source_registry.py`
- `scripts/test_source_registry_verify_checks.py`
- `src/reference/source_scoring.py`

### 完了内容

- default registry: 59 sources、active 6、fetch_enabled 0、X active 0、beauty 23、beauty_future target 0。
- production example: 91 sources、active 0、fetch_enabled 0、beauty_future target 0。
- recovered shared: 3 Threads sources。
- 全 source に `use_policy=REFERENCE_ONLY` / `can_reuse_media=false` を明示。
- beauty source は `rights_policy=reference_only` / `usage_scope=future_reference_only` / `review_status=BLOCKED_BEAUTY_ACCOUNT` / `default_queue_status=WAITING_REVIEW`。
- `source_rows()` と Sheets headers に safety columns を追加。既存列は削除・並び替えなし。
- `seed_source_registry.py` は `beauty_account` target alias と `query` platform filter に対応。`beauty_future` は filter alias のみ。
- verify checks に `beauty_target_account_id_preserved` / `beauty_reference_only_safety` を追加。

### 未完了事項

- Sheets への実 seed apply は未実行。必要時のみ `python3 scripts/seed_source_registry.py --apply --confirm-seed --target-account all --platform all` を人間承認後に実行。
- live Sheets verify は未実行。外部 Sheets 読み取りになるため、今回は local/unit/dry-run で確認。
- 実 fetch/download/cut/upload/post は未実行。

### スケール方針

- source は `default_sources.json` に追加し、`source_rows()` を通して Sheets へ反映する。並行 writer/schema は作らない。
- X は reference/manual のまま。自動 fetch/post の対象にしない。
- third-party media は `can_reuse_media=false` 既定。権利許諾が明示されるまで download/cut/upload/post 利用しない。
- scoring は並び替え・候補提示のみ。source priority の自動変更は禁止。

### 残WARN

- `src/reference/source_scoring.py` は helper とテスト接続済みだが、本番の採点CLI本線への深い接続は次フェーズ。
- `recover_production_sheets_threads_first.py --verify-only` は live Sheets 読み取りのため、今回は未実行。
- 旧 repo workflow 停止は引き続き人間作業。

### 全テスト結果

- `python3 -m py_compile ...`: PASS
- `python3 scripts/test_seed_source_registry.py`: PASS 10 / FAIL 0
- `python3 scripts/test_source_registry_verify_checks.py`: PASS 11 / FAIL 0
- `python3 scripts/test_phase13_production_sources_real_urls.py`: PASS 1 / FAIL 0
- `python3 scripts/test_phase13_source_registry_production.py`: PASS 28 / FAIL 0
- `python3 scripts/test_phase13_query_source_support.py`: PASS 5 / FAIL 0
- `python3 scripts/test_phase13_article_source_support.py`: PASS 5 / FAIL 0
- `python3 scripts/test_source_account_registry.py`: PASS 27 / FAIL 0
- `python3 scripts/test_beauty_account_block.py`: PASS 9 / FAIL 0
- `python3 scripts/test_no_beauty_ready_queue.py`: PASS 4 / FAIL 0
- `python3 scripts/test_no_x_ready_queue.py`: PASS 4 / FAIL 0
- `python3 scripts/test_media_policy_guard.py`: PASS 8 / FAIL 0
- `python3 scripts/test_recover_verify_ready_checks.py`: PASS 10 / FAIL 0
- `python3 scripts/test_phase13_pipeline_store.py`: PASS 15 / FAIL 0
- `python3 scripts/test_phase13_source_fetcher_tool_doctor.py`: PASS 29 / FAIL 0
- `python3 scripts/test_phase13_fetcher_production_paths.py`: PASS 2 / FAIL 0
- `python3 scripts/test_phase13_source_to_post_production_path.py`: PASS 4 / FAIL 0
- `python3 scripts/test_phase13_publishers_production_safety.py`: PASS 4 / FAIL 0
- `python3 scripts/test_phase13_generation_production.py`: PASS 3 / FAIL 0
- `python3 scripts/test_phase13_real_smoke_plan.py`: PASS 18 / FAIL 0
- `python3 scripts/test_phase13_pdca_production_loop.py`: PASS 3 / FAIL 0
- `python3 scripts/test_phase13_media_asset_storage.py`: PASS 3 / FAIL 0
- `python3 scripts/test_phase13_video_clip_execution.py`: PASS 3 / FAIL 0
- `python3 scripts/test_phase13_media_post_preflight.py`: PASS 3 / FAIL 0
- `python3 scripts/test_phase13_source_lifecycle.py`: PASS 23 / FAIL 0
- `python3 scripts/test_phase13_source_concept_matching.py`: PASS 4 / FAIL 0
- `python3 scripts/test_phase11_source_to_post_orchestrator.py`: PASS 23 / FAIL 0
- `python3 scripts/test_approve_queue_ready_transition.py`: PASS 11 / FAIL 0
- `python3 scripts/test_refill_outputs_waiting_review_not_ready.py`: PASS 4 / FAIL 0
- `python3 scripts/test_queue_worker_no_setup_all_in_real_mode.py`: PASS 12 / FAIL 0
- `python3 scripts/test_phase60_thread_series.py`: PASS 21 / FAIL 0
- `python3 scripts/test_thread_series_learning_loop.py`: PASS 11 / FAIL 0
- `python3 scripts/test_phase10_threads_publisher.py`: PASS 7 / FAIL 0
- `python3 scripts/test_phase10_x_publisher.py`: PASS 5 / FAIL 0
- `python3 scripts/test_phase10_publishers_safety.py`: PASS 14 / FAIL 0

### dry-run / BLOCKED確認結果

- `python3 scripts/seed_source_registry.py --dry-run --target-account all --platform all`: PASS、59 source_accounts / 33 reference_sources、Sheets writeなし。
- `python3 scripts/seed_source_registry.py --apply --target-account all --platform all --json`: `--confirm-seed` なしのため dry-run扱い、Sheets writeなし。
- `python3 scripts/seed_source_registry.py --dry-run --target-account beauty_account --platform youtube --json`: PASS、10 source_accounts / 10 reference_sources。
- `python3 scripts/seed_source_registry.py --dry-run --target-account beauty_future --platform tiktok --json`: PASS、7 source_accounts / 7 reference_sources。
- `python3 scripts/seed_source_registry.py --dry-run --target-account all --platform query --json`: PASS、1 source、fetch_enabled=false。

### confirmなしBLOCKED確認結果

- confirmなし seed apply: dry-run扱いでBLOCKED相当。
- confirmなし fetch/download/cut/upload/post は既存 Phase13 tests で BLOCKED/PASS 確認済み。

### 次にClaude Codeが触ってよいファイル

- `config/source_accounts/default_sources.json`（source追加・安全field維持）
- `scripts/seed_source_registry.py`（Sheets applyの表示改善、429 backoff改善）
- `src/reference/source_scoring.py`（本番採点CLIへの接続）
- `docs/source-recovery-and-seed.md`

### 次にCodexが触ってよいファイル

- `scripts/recover_production_sheets_threads_first.py`
- `src/sheets_client.py`
- `scripts/test_seed_source_registry.py`
- `scripts/test_source_registry_verify_checks.py`
- Phase13 source/media/publisher safety tests

### 衝突しやすいファイル

- `config/source_accounts/default_sources.json`
- `config/source_accounts/production_sources.example.json`
- `scripts/recover_production_sheets_threads_first.py`
- `src/sheets_client.py`
- `docs/ai-work-handoff.md`

### 触らない方がいいファイル

- `.env` / token / cookie / credential files
- `data/threads_tokens`
- `output/media_cache` / `cloudinary_cache`
- 旧 repo の任意ファイル
- `config/accounts/beauty_account.json` の `draft_only` 解除

### 次AIへの引き継ぎメモ

- `beauty_future` を target account にしない。必ず `target_account_ids=["beauty_account"]` を維持する。
- 実 Sheets 反映が必要なら、まず `seed_source_registry.py --dry-run` の件数を確認し、その後だけ `--apply --confirm-seed`。
- `source_rows()` は source registry の安全ゲート。新しい field を Sheets に出す場合は `src/sheets_client.py` のヘッダーにも末尾追加する。
- 実投稿・実fetch・download/cut/upload・Cloudinary upload・transcription API はこの作業では一切実行していない。

## Codex required source URL照合・追加 (2026-06-29 追記)

### 現在のHEAD / ブランチ

- 作業ブランチ: `main`
- 作業開始HEAD: `1e8966b5e3376d1cb4c7b117626df32317f660a4`
- 完了commit: この変更を含む最終 `main` HEAD は `git rev-parse HEAD` と最終レポートを参照

### 本システムについて

- ユーザー明示URLは `config/source_accounts/required_source_urls.json` を authoritative list とする。
- 今後 required URL が追加されたら、この JSON に追記し、required source tests を通す。
- X status URL は profile source と別に `post_url` / `canonical_url` / `status_url` で保持できるようにした。

### 変更ファイル一覧

- `config/source_accounts/default_sources.json`
- `config/source_accounts/required_source_urls.json`
- `scripts/required_source_url_checks.py`
- `scripts/test_required_source_urls_present.py`
- `scripts/test_required_threads_sources_present.py`
- `scripts/test_required_x_sources_manual_only.py`
- `scripts/test_source_canonical_url_matching.py`
- `scripts/test_no_fetch_enabled_required_sources.py`
- `scripts/test_required_sources_classification.py`
- `scripts/recover_production_sheets_threads_first.py`
- `src/sheets_client.py`
- `docs/source-account-registry.md`
- `docs/source-recovery-and-seed.md`
- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`

### 完了内容

- required Threads URL 6件を全件照合。既存2件、追加4件。
- required X URL 7件を全件照合。6件はURL一致済み、`minatoku789` status URLは既存sourceへ保持。
- `default_sources.json`: 59件 → 63件。
- `active`: 6件 → 10件（追加Threads 4件は `active=true`）。
- `fetch_enabled=true`: 0件維持。
- `night_scout`: 21件 → 25件、`liver_manager`: 15件維持、`beauty_account`: 23件維持。
- `target_account_ids=["beauty_future"]`: 0件維持。
- YouTube/TikTok再探索: production example の33件はすべて default に存在。追加すべき未登録の実source account URLはなし。

### 未完了事項 / 残WARN

- `recover_production_sheets_threads_first.py --verify-only --json` は承認システム側の out of credits で実行拒否。Sheets apply/write は未実行。
- 実fetch / 実download / 実cut / 実upload / 実投稿 / Cloudinary upload / transcription API は未実行。

### 全テスト結果

- `python3 -m py_compile ...`: PASS
- `python3 scripts/test_required_source_urls_present.py`: PASS 1 / FAIL 0
- `python3 scripts/test_required_threads_sources_present.py`: PASS 1 / FAIL 0
- `python3 scripts/test_required_x_sources_manual_only.py`: PASS 1 / FAIL 0
- `python3 scripts/test_source_canonical_url_matching.py`: PASS 1 / FAIL 0
- `python3 scripts/test_no_fetch_enabled_required_sources.py`: PASS 1 / FAIL 0
- `python3 scripts/test_required_sources_classification.py`: PASS 1 / FAIL 0
- `python3 scripts/test_seed_source_registry.py`: PASS 10 / FAIL 0
- `python3 scripts/test_source_registry_verify_checks.py`: PASS 11 / FAIL 0
- `python3 scripts/test_phase13_production_sources_real_urls.py`: PASS 1 / FAIL 0
- `python3 scripts/test_beauty_account_block.py`: PASS 9 / FAIL 0
- `python3 scripts/test_no_beauty_ready_queue.py`: PASS 4 / FAIL 0
- `python3 scripts/test_media_policy_guard.py`: PASS 8 / FAIL 0

### dry-run / verify結果

- `python3 scripts/seed_source_registry.py --dry-run --target-account all --platform all`: PASS、63 source_accounts / 33 reference_sources、`fetch_enabled_true=0`、Sheets writeなし。
- `python3 scripts/recover_production_sheets_threads_first.py --verify-only --json`: 未実行（approval credits拒否）。外部API回避は行っていない。

### 次AIへの引き継ぎメモ

- required URLの追加は `config/source_accounts/required_source_urls.json` と `default_sources.json` の両方を更新する。
- `test_required_source_urls_present.py` が required URL抜けの防止ゲート。
- X required source は `manual_only=true` / `active=false` / `fetch_enabled=false` を維持し、X APIやqueueに接続しない。
- Threads required source は `night_scout` 用。実fetchはせず、manual/reference sourceとして保持する。
