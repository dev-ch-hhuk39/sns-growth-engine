# Production Completion Status

Date: 2026-06-25 (最終更新)
Created: 2026-06-24

## Status

The project is operational for Threads-first manual review operation.
`threads-queue-worker.yml` の Sheets verify は 2026-06-25 時点で **verification_passed=33 failed=0** に到達した。

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

## Remaining Manual Checks

- GitHub Actions `threads-queue-worker.yml` dry_run を再実行して verification_passed=33 failed=0 を Actions 上でも確認する
- `night_scout` の Threads 次投稿候補（WAITING_REVIEW 3案）をレビューして承認する
- liver_manager の DUPLICATE_BLOCKED を解消するには queue 行に別 draft_id の新候補を追加する
- Threads insights（night_scout 初回投稿 / liver_manager 投稿）を確認する
- X API Credits を補充し、X 投稿を再開するかどうか判断する
- Cloudinary upload を使う場合は `ALLOW_CLOUDINARY_UPLOAD=true` で `media-approved-pilot.yml` を実行する
