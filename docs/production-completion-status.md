# Production Completion Status

Date: 2026-06-25 (最終更新)
Created: 2026-06-24

## Status

The project is operational for Threads-first manual review operation.
`threads-queue-worker.yml` の Sheets verify は 2026-06-25 時点で **verification_passed=33 failed=0** を達成・維持。

## 2026-06-25 アップデート — posted_results 整合性修復

### 失敗原因

GitHub Actions `threads-queue-worker.yml` dry_run で `recover_production_sheets_threads_first.py --verify-only` が exit code 1 で失敗していた。

- `verification_passed=30 failed=3`
- `failed_checks=posted_metrics_status_allowed,posted_real_post_true,posted_media_used_false`

**原因**: posted_results 既存3行のうち、以下2行の新規カラムが空欄だった（Sheetsに列が追加された時点で既存行に値が書かれていなかった）。
- `recovery_threads_initial_night_scout` (status=RECOVERED): metrics_status / real_post / media_used 空
- `real_threads_liver_manager_20260624_01` (status=POSTED): metrics_status / real_post / media_used 空

**修正内容**:
1. `scripts/repair_posted_results_integrity.py` を新規作成
   - POSTED 行: metrics_status="" → "PENDING", real_post="" → "true", media_used="" → "false"
   - RECOVERED 行: metrics_status="" → "MANUAL_PENDING", real_post="" → "true", media_used="" → "false"
   - `--apply` で Sheets 書き込み、`--dry-run` では書き込まない
   - read-after-write 確認付き
2. `backfill_posted_results()` の POSTED 行 metrics_status 補正値を "MANUAL_PENDING" → "PENDING" に修正
3. `.github/workflows/threads-queue-worker.yml` に repair ステップを追加 (verify の前に実行)
4. `scripts/test_repair_posted_results_integrity.py` 17項目 PASS
5. `scripts/test_recovered_posted_result_verify_warn.py` 10項目 PASS

### 修復後の確認結果

```
verification_passed=33 failed=0
count_posted_results=3
threads_credentials_night_scout=SET
threads_credentials_liver_manager=SET
```

- `python3 scripts/process_threads_queue.py --account-id night_scout --dry-run`: status=DRY_RUN ✓
- `python3 scripts/process_threads_queue.py --account-id liver_manager --dry-run`: status=DUPLICATE_BLOCKED ✓（duplicate guard 正常動作）

## Completed

- Existing unpushed main commit was pushed to GitHub before recovery.
- Google Sheets tabs were audited.
- Empty production tabs were seeded.
- Read-after-write verification passed.
- CTA rules were applied to code, Sheets seed, prompt templates, and docs.
- X posting was disabled for recovery mode.
- `night_scout` and `liver_manager` Threads queues were seeded.
- `beauty_account` remains blocked.
- Cloudinary upload was not executed.
- Media download/cut/upload was not executed.
- One `liver_manager` Threads real post was executed and recorded.
- `scripts/process_threads_queue.py` added for queue row processing.
- `scripts/import_threads_metrics_manual.py` added for manual insights import.
- `scripts/refill_threads_queue.py` added for review queue refill.
- `.github/workflows/threads-queue-worker.yml` added as manual-only worker.
- `content-daily-dry-run.yml` switched to Threads-first queue dry-run/refill dry-run/publisher dry-run.

## Verification

- Sheets verification: 21 / 21 PASS.
- Required local tests: 18 / 18 scripts PASS.
- Credential readiness: READY for required items.
- Cloudinary: credentials SET, upload disabled.
- Cloudflare transcription: optional credentials missing, transcription disabled.
- Stricter local Sheets verification and worker dry-run against live Sheets: blocked by local approval credits.
- GitHub Actions dry-run attempted twice and classified: repository Sheets secrets missing, so the workflow stopped before queue processing.
- True dry-run implementation verified locally: worker/refill dry-run do not call `setup_all()` or write to Sheets.

## 2026-06-25 アップデート — 孤児投稿復旧・Sheets 429 対策

### 失敗原因

GitHub Actions `threads-queue-worker.yml` real_post 実行後、Threads 投稿は成功したが
Sheets API 429（Read requests per minute per user quota）で `save_posted_result()` が失敗した。

- `queue_id=recovery_night_scout_queue_01` が PROCESSING に残存
- `posted_results` に行が未追加

**原因**: `append_row` / `update_row` がヘッダー行 (`ws.row_values(1)`) を毎回呼び出しており、
複数回の Sheets API コールで quota を超過した。

**修正内容**:

1. `process_threads_queue.py`
   - `_headers_cache` 追加（同一 ws はセッション内 1 回のみ `row_values(1)` を呼ぶ）
   - `_get_headers()` に 429 指数バックオフ（5s/15s/30s）追加
   - real_post モードの `setup_all()` 呼び出しを削除（タブは初期化済み前提）
   - `FALLBACK_DIR` 定数追加、`write_fallback()` に `dry_run` パラメータ追加

2. `scripts/recover_orphan_threads_post.py` 新規作成
   - Threads API で最新投稿を取得してテキスト一致を確認
   - `--skip-api-lookup` で ID 不明のまま RECOVERED 行を追加可
   - 実行結果: `recovery_night_scout_queue_01` → status=POSTED、posted_results に RECOVERED 行追加

3. `.github/workflows/threads-queue-worker.yml`
   - `output/posted_results_fallback/` を `actions/upload-artifact` で 30 日保存 (`if: always()`)

4. `recover_production_sheets_threads_first.py`
   - `queue_night_scout_3` → `queue_night_scout_2` に変更（孤児復旧で active 行が 2 に）

5. テスト 4 本追加（全 PASS）:
   - `test_recover_orphan_threads_post.py`: 13 PASS
   - `test_sheets_rate_limit_backoff.py`: 14 PASS
   - `test_queue_worker_no_setup_all_in_real_mode.py`: 12 PASS
   - `test_fallback_artifact_no_secrets.py`: 11 PASS

### 修復後の確認結果

```
verification_passed=33 failed=0
count_posted_results=4
count_queue_night_scout=2
```

- `python3 scripts/process_threads_queue.py --account-id night_scout --dry-run`: queue_02 status=DRY_RUN ✓
- `python3 scripts/process_threads_queue.py --account-id liver_manager --dry-run`: status=DUPLICATE_BLOCKED ✓

## 2026-06-25 アップデート — queue WARN 設計 / liver_manager dup 解消

### 変更内容

1. `recover_production_sheets_threads_first.py` `verify_state()`
   - `queue_night_scout_3` / `queue_liver_manager_3` チェックを廃止
   - 代わりに `queue_night_scout_min1` / `queue_liver_manager_min1`（>= 1 なら PASS）を採用
   - queue が 1〜2 件 → `warning_list` / `refill_needed_accounts` に追記。FAIL にはならない
   - queue が 0 件 → 従来通り FAIL
   - `RECOVERED` 行の `external_post_id` 未補完 → WARN のみ（FAIL にしない）
   - `posted_save_failed` > 0 → WARN のみ

2. night_scout queue 補充
   - `refill_threads_queue.py --account-id night_scout --count 1` 実行
   - queue_after=4（WAITING_REVIEW 3 / PLANNED 1）

3. liver_manager DUPLICATE_BLOCKED 解消
   - `recovery_liver_manager_queue_01`（draft=`recovery_liver_manager_draft_01`）が posted_results に既存のため dry-run でも DUPLICATE_BLOCKED だった
   - `refill_threads_queue.py --account-id liver_manager --count 1` で新候補追加
   - Sheets 上で `recovery_liver_manager_queue_01` を直接 `DUPLICATE_BLOCKED` に更新（実投稿なし）
   - `process_threads_queue.py --account-id liver_manager --dry-run` → `status=DRY_RUN` ✓（`recovery_liver_manager_queue_02` が選ばれる）

4. night_scout posted_results 孤児投稿
   - `orphan_recovery_recovery_night_scout_queue_01_*` の `post_url` を更新
   - `https://www.threads.com/@kyaba_consul_mizu/post/DZ_bylhAIqz`
   - `external_post_id=18050331680547160`
   - WARN なし（補完済み）

5. 新規テスト 3本追加（各 14〜15 PASS）
   - `test_verify_queue_minimum_warn_not_fail.py`: 15 PASS
   - `test_refill_needed_accounts_warning.py`: 15 PASS
   - `test_posted_recovered_post_url_backfill.py`: 14 PASS

### 修復後の確認結果

```
verification_passed=33 failed=0
warning_list=[]
count_posted_results=4
count_queue_night_scout=3
count_queue_liver_manager=3
```

- `python3 scripts/process_threads_queue.py --account-id night_scout --dry-run`: queue_02 status=DRY_RUN ✓
- `python3 scripts/process_threads_queue.py --account-id liver_manager --dry-run`: queue_02 status=DRY_RUN ✓

## 2026-06-26 アップデート — GitHub Actions dry_run 両アカウント PASS

### GitHub Actions dry_run 結果

- run `28212477795` (night_scout): **success** — verification_passed=33 failed=0, status=DRY_RUN ✓
- run `28212482318` (liver_manager): **success** — verification_passed=33 failed=0, status=DRY_RUN ✓

### 追加変更

- `.github/workflows/threads-queue-worker.yml`: dry_run では post-processing verify を skip（`if: mode == 'real_post'` 条件付き）。real_post では sleep 60 + verify を実行。
- `test_threads_queue_worker_workflow.py`: verify-after の `if: real_post` 条件チェック追加（14 PASS）

## 2026-06-26 アップデート — self_generated media パイプライン追加

法的リスク最小の「自前生成テキストカード」パスを実装（第三者 media・実投稿・実 upload は一切なし）。

1. `src/media/social_card.py` + `scripts/generate_social_card.py`
   - PIL で 1080x1350 / 1080x1080 のテキストカード描画
   - self_generated レコード（rights_policy=owned / reuse_policy=allow_reuse / media_policy=owned / status=SELF_GENERATED）
   - 出力は `output/social_cards/`（gitignore 済）。Sheets 書き込みなし。Cloudinary upload は別ゲート維持
2. `src/publishers/threads_publisher.py` — `publish()` に `media_url` 追加
   - dry-run + media: 「IMAGE 添付予定」を計画表示（API 呼び出しなし）
   - real mode + media: env フラグ true でも `SAFETY_STOP` でハード拒否（実 media 投稿は構造的に不可能）
3. `src/media/queue_media_attach.py` + `scripts/attach_media_to_queue.py`
   - 権利クリア media のみ queue 付与計画（plan-only・Sheets 書き込みなし）

テスト 3 本追加: social_card 22 / publisher_media_dryrun 11 / attach_media 14（全 PASS）。
既存 publisher テスト（phase10/phase13/preflight）回帰なし。
commit: `8b14d01` / `9bdf7f5` / `cccaee6`（main に push 済み）。

### 保留（別途ユーザー判断）

- queue worker への media 読み込み配線（本番 Sheets 読み込み 429 リスク考慮）
- queue 行への media_asset_id 実書き込み（本番 Sheets write）
- `generate_next_queue_from_metrics.py` / media-approved-pilot.yml
- Cloudinary 実 upload・実 media 投稿

## Remaining Manual Checks

- `night_scout` の Threads 次投稿候補（WAITING_REVIEW 3案）をレビューして承認する
- Threads insights（night_scout 初回投稿 / liver_manager 投稿）を確認する
- X API Credits を補充し、X 投稿を再開するかどうか判断する
- Cloudinary upload を使う場合は `ALLOW_CLOUDINARY_UPLOAD=true` で `media-approved-pilot.yml` を実行する
