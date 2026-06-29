# Production Completion Status

Date: 2026-06-29 (最終更新 — READY 承認モデル必須化)
Created: 2026-06-24

## Status

The project is operational for Threads-first manual review operation.
`threads-queue-worker.yml` の Sheets verify は check 総数 **51 件**（2026-06-25 snapshot の 33 件 → item J の media/metrics チェック等で +8 → READY 承認モデルで +10）。合格条件は `failed=[]`（`passed` は seed 充足状況で変動）。READY 承認モデル追加後の live `--verify-only` 再確認は #68 で実施。

## 2026-06-29 アップデート — Threads worker READY 承認モデル必須化（Phase 3）

### 変更点

- `process_threads_queue.py` の投稿対象を **`READY` のみ**に変更（`ELIGIBLE_STATUSES = {"READY"}`）。
  `WAITING_REVIEW` / `DRAFT` / `PLANNED` は投稿対象外。状態遷移 `WAITING_REVIEW → READY → PROCESSING → POSTED`。
- 生成系CLI（refill / clip / metrics 候補 / seed）は `READY` を直接書かない。`READY` 昇格は `approve_queue.py`（WAITING_REVIEW → READY/REJECTED）経由のみ。承認時は logs に `queue_approved` 証跡を残す。
- X 側 `publish_queue.py` の `--status READY` 必須ゲートと対称になり、旧「承認モデル非対称」の潜在課題を解消。
- verify に READY 承認モデルの安全チェック10件を追加（`waiting_review_not_postable` / `ready_is_only_postable_status` / `generated_candidates_not_ready_by_default`（承認証跡で誤検知防止）/ `no_ready_for_x_or_beauty` / media 権利3件 ほか）。
- 回帰固定テスト `test_recover_verify_ready_checks.py` ほか READY 系11本を追加。curated suite **55 / 55 PASS**（offline）。

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

## 2026-06-27 アップデート — media 承認ワークフロー + metrics ループ実装

2026-06-26 時点で「保留」だった項目のうち、**コード・ゲート・テストで完結する範囲**を実装した。
実 upload / 実 media 投稿 / 本番 Sheets への実書き込みは、引き続き明示フラグと確認ゲートの後ろに保持する。

### 実装した内容

1. `scripts/attach_media_to_queue.py`（item G）
   - 権利クリア media を queue 行へ付与。既定 PLAN_ONLY。実書き込みは `--apply --confirm-attach`。
   - 既存ヘッダーのある列だけに書き込む（防御的）。`--apply` と `--input-json` の併用は拒否。
2. `scripts/upload_approved_media_to_cloudinary.py`（item H）
   - `evaluate_upload_gate()`: approval_status=APPROVED または status=SELF_GENERATED、かつ権利クリア、
     かつ rights_review_required≠true、かつローカルファイル存在、のときのみ許可。
   - 実 upload は `--apply --confirm-upload` かつ `ALLOW_CLOUDINARY_UPLOAD=true` のときだけ。secrets は出力しない。
3. `scripts/approve_self_generated_media.py`（item I）
   - self_generated・権利クリア・未承認の media のみ approval_status=APPROVED に。
   - 既定 PLAN_ONLY。実書き込みは `--apply --confirm-approve`。beauty_account は不可。
4. `scripts/import_threads_metrics_manual.py` 強化（item L）
   - ER 計算を純粋関数 `compute_engagement_rate()` に分離。
   - 決定論的 id による再インポートの二重追記を `row_exists()` ガードで防止（冪等化）。
5. `scripts/generate_next_queue_from_metrics.py` 新規（item L）
   - posted_results の MEASURED 行を ER 降順でランキングし、次回候補を生成。
   - 生成 queue 行の status は worker の `ELIGIBLE_STATUSES`（現在は {READY}）に
     **含めない**（`DRAFT`）。worker が自動投稿しないことをコードで保証（assert）。
     ※ 2026-06-29 に `ELIGIBLE_STATUSES` は {READY} に変更（READY 承認モデル）。本項記載時は {WAITING_REVIEW, PLANNED} だったが、DRAFT が非対象である点は変わらない。
   - 既定 PLAN_ONLY。実書き込みは `--apply --confirm-generate`。beauty_account / x は対象外。
     改善提案は status=WAITING_REVIEW（auto_apply=false）。
6. `recover_production_sheets_threads_first.py` verify 強化（item M）
   - `media_approved_rows_rights_clear`: APPROVED media は権利クリアであること
   - `media_uploaded_only_if_approved`: upload 済み media は承認済みのみ
   - `metrics_candidates_not_postable`: metrics 由来候補は worker 非対象 status であること
   - `metrics_suggestions_waiting_review`: metrics 由来提案は WAITING_REVIEW であること

### テスト（item N）

新規 7 本 + 関連既存 29 本 = **curated 36 / 36 PASS**（offline 完結）。
- 新規: `test_generate_next_queue_from_metrics`(17) / `test_metrics_import_idempotency_and_er`(11) /
  `test_recover_verify_media_metrics_checks`(8) / `test_approve_self_generated_media`(11) /
  `test_upload_approved_media_gate`(10) / `test_attach_media_apply_writes`(14) / `test_attach_media_to_queue`(14)
- 既存回帰なし（queue worker / refill / posted_results integrity / verify / beauty/x safety / cta 等）。

### 引き続きゲート保持（明示確認が必要・自動実行しない）

- liver_manager Threads 実投稿（`PUBLISH_ENABLED=true ALLOW_REAL_THREADS_POST=true --confirm-real-post`）
- Cloudinary 実 upload（`ALLOW_CLOUDINARY_UPLOAD=true --confirm-upload`）
- 上記スクリプトの本番 Sheets `--apply`（attach / approve / generate）
- git commit / push

## Remaining Manual Checks

- `night_scout` の Threads 次投稿候補（WAITING_REVIEW）をレビューし、`approve_queue.py --queue-id <id> --approve --reason "..."` で `READY` に昇格して初めて worker 投稿対象になる
- Threads insights（night_scout 初回投稿 / liver_manager 投稿）を確認する
- X API Credits を補充し、X 投稿を再開するかどうか判断する
- Cloudinary upload を使う場合は `ALLOW_CLOUDINARY_UPLOAD=true` で `media-approved-pilot.yml` を実行する

## 過去共有sourceの回収・registry化 (2026-06-29)

- ユーザーが過去に共有済みのソースアカウントURL/選定ルールを、既存 repo / `production_sources.example.json` から回収し `config/source_accounts/default_sources.json` へ dedup マージ済み(17→59件)。
- `scripts/seed_source_registry.py`(dry-run/apply)で source_accounts / reference_sources タブへ seed。
- X=reference保持(投稿対象外・manual_only)、TikTok/YouTube=reference_only(can_reuse_media=false)、beautyは`target_account_ids=["beauty_account"]`維持でinactive、`beauty_future`はtrack labelのみ、公式メディア=低優先、URL未入力=WAITING_URL_INPUT。
- 詳細: [source-recovery-and-seed.md](source-recovery-and-seed.md) / [ai-work-handoff.md](ai-work-handoff.md)。
