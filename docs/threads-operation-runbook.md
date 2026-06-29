# Threads Operation Runbook

## Current Mode

The system is now Threads-first.

- `night_scout`: Threads enabled, X posting disabled.
- `liver_manager`: Threads enabled, X posting disabled.
- `beauty_account`: draft-only, real posting disabled.

## 投稿可否モデル（READY 承認モデル）

worker が投稿するのは **`READY` の行のみ**。生成系CLIが出力する行は既定で `WAITING_REVIEW`（レビュー待ち）であり、人間が内容を確認したうえで `approve_queue.py` で `READY` に昇格させて初めて投稿対象になる。`WAITING_REVIEW` のまま投稿されることはない。

状態遷移: `WAITING_REVIEW → READY → PROCESSING → POSTED`（昇格は `approve_queue.py` 経由のみ）。詳細は `docs/threads-queue-worker.md` の Status モデルを参照。

## Daily Safe Flow

1. Verify Sheets state:

```bash
python3 scripts/recover_production_sheets_threads_first.py --verify-only
```

2. Review `投稿キュー`. `WAITING_REVIEW` の行を一覧で確認する:

```bash
python3 scripts/approve_queue.py --account-id <account_id> --status WAITING_REVIEW --list
```

3. 内容を確認した行のみ `READY` に昇格させる（人間承認）:

```bash
python3 scripts/approve_queue.py --queue-id <queue_id> --approve --reason "<確認内容>"
# 却下する場合
python3 scripts/approve_queue.py --queue-id <queue_id> --reject --reason "<理由>"
```

4. Run queue worker dry-run（`READY` のみ拾う）:

```bash
python3 scripts/process_threads_queue.py --account-id <account_id> --dry-run
```

Dry-run is read-only: it does not run `setup_all()`, create tabs, add headers, update queue rows, append logs, save posted_results, create PDCA rows, or write fallback JSON.

5. For real post, execute only one row at a time and never retry immediately after failure（`READY` 行のみ対象。実投稿は triple gate `--confirm-real-post` + `PUBLISH_ENABLED=true` + `ALLOW_REAL_THREADS_POST=true` が揃ったときのみ）:

```bash
PUBLISH_ENABLED=true ALLOW_REAL_THREADS_POST=true \
python3 scripts/process_threads_queue.py --account-id <account_id> --confirm-real-post --max-posts 1
```

6. Import Threads metrics manually after enough time has passed:

```bash
python3 scripts/import_threads_metrics_manual.py --result-id <result_id> --views 0 --likes 0 --comments 0 --follows 0 --dry-run
```

7. Refill review queue only after checking pending rows（`refill` の出力は `WAITING_REVIEW`。直接 `READY` にはならない）:

```bash
python3 scripts/refill_threads_queue.py --account-id <account_id> --count 1 --dry-run
```

## Hard Stops

- Do not post `beauty_account`.
- Do not run X posting.
- Do not promote rows to `READY` without human review (生成系CLIに `READY` を直接書かせない).
- Do not post `WAITING_REVIEW` / `DRAFT` / `PLANNED` rows.
- Do not download/cut/upload media.
- Do not enable Cloudinary upload.
- Do not enable transcription API.
- Do not set learning rules active automatically.
- Do not repost rows with `POSTED`, `PROCESSING`, `FAILED`, `POSTED_SAVE_FAILED`, or `DUPLICATE_BLOCKED`.

## Current Live Post State

- `night_scout`: first Threads post already completed before this recovery.
- `liver_manager`: one Threads post was executed during the 2026-06-24 recovery and recorded in `投稿結果`.

## Worker References

- Queue worker: `docs/threads-queue-worker.md`
- Metrics import: `docs/metrics-import-runbook.md`
- Manual Sheets checks: `docs/sheets-manual-check-guide.md`

## GitHub Actions Manual Run

Before running, confirm repository secrets include:

- `SNS_MASTER_SHEET_ID` or `SPREADSHEET_ID`
- `SA_JSON_BASE64` or `GCP_SA_JSON_BASE64`

Then open GitHub Actions > `Threads Queue Worker` > `Run workflow`:

- `account_id`: `night_scout` or `liver_manager`
- `mode`: `dry_run`
- `max_posts`: `1`
- `confirm_real_post`: `false`

Do not use `real_post` until dry-run has passed and one queue row has been reviewed.
