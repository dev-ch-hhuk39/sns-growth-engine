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

## 2026-06-30 current review targets

Source registry由来の初回投稿案は、以下のprefixで確認する。

- `投稿キュー`: `q_night_scout_manualref_...` 3件、`q_liver_manager_manualref_...` 3件
- `SNS投稿文`: `idea_night_scout_manualref_...` 3件、`idea_liver_manager_manualref_...` 3件
- `収集済み投稿`: `manualref_...` 10件
- `参考投稿スコア`: `qscore_...` 10件

現在 `READY=0`。人間が1件だけ選び、以下を実行するまでは投稿worker対象にならない。

```bash
python3 scripts/approve_queue.py --queue-id <queue_id> --approve --reason "<確認内容>" --use-sheets
python3 scripts/process_threads_queue.py --account-id <account_id> --dry-run --max-posts 1
```

実投稿へ進むのは、dry-runで対象テキスト・アカウント・重複・media状態を確認した後の別作業とする。

## AUTO_READY運用

READY承認は、手動だけでなくAUTO_READYで条件付き自動化できる。

```bash
python3 scripts/auto_approve_queue.py --dry-run --account-id all --max-ready 2 --use-sheets
python3 scripts/auto_approve_queue.py --apply --confirm-auto-ready --account-id all --max-ready 2 --use-sheets
python3 scripts/process_threads_queue.py --account-id night_scout --dry-run --max-posts 1
python3 scripts/process_threads_queue.py --account-id liver_manager --dry-run --max-posts 1
```

現在はAUTO_READYで2件READY化済み。実投稿は未実行。

- `READY`: 2件
- `WAITING_REVIEW`: 8件
- `auto_post_enabled=false`
- 実投稿には `PUBLISH_ENABLED=true ALLOW_REAL_THREADS_POST=true` と `--confirm-real-post` が必要

AUTO_POSTを有効化する場合も `run_autopilot_loop.py --auto-post` だけでは投稿されない。設定側の `auto_post_enabled=true`、env gate、`--confirm-real-post` が全て必要。

## 2026-06-30 first real post result

1件だけ実投稿を実施済み。再実行しないこと。

- account: `liver_manager`
- queue_id: `q_liver_manager_manualref_src_lm_note_cand_001_threads`
- result_id: `threads_q_liver_manager_manualref_src_lm_note_cand_001_threads_20260630025810`
- post_url: `https://www.threads.com/@ran.liver_pro/post/DaMbCLQiXLs`
- queue status: `POSTED`
- posted_results: `POSTED`, `metrics_status=PENDING`, `real_post=TRUE`, `media_used=FALSE`

実投稿後の確認:

```bash
python3 scripts/recover_production_sheets_threads_first.py --verify-only --json
python3 scripts/import_threads_metrics_manual.py --result-id threads_q_liver_manager_manualref_src_lm_note_cand_001_threads_20260630025810 --views 0 --likes 0 --comments 0 --follows 0 --profile-clicks 0 --line-adds 0 --memo "first post metrics dry-run template" --dry-run
python3 scripts/generate_next_queue_from_metrics.py --dry-run --account-id liver_manager
```

運用メモ:

- metrics実測値が取れるまでは `metrics_status=PENDING` のまま。
- metrics applyは人間が数値を確認してから行う。
- 次の実投稿候補は `night_scout` のREADY 1件のみ。必ずdry-runで対象確認してから、別作業で1件だけ実行する。
- `PUBLISH_ENABLED=true` と `ALLOW_REAL_THREADS_POST=true` はコマンドスコープでのみ使う。

## Scheduled AUTO_READY pilot

`.github/workflows/autopilot-auto-ready.yml` を追加した。6時間ごとにAUTO_READYまでを実行する設計で、投稿はしない。

安全条件:

- `PUBLISH_ENABLED=false`
- `ALLOW_REAL_THREADS_POST=false`
- `ALLOW_REAL_X_POST=false`
- `ALLOW_TRANSCRIPTION_API=false`
- `ALLOW_CLOUDINARY_UPLOAD=false`
- `run_autopilot_loop.py --apply --confirm-run --auto-ready --skip-real-post`
- `--confirm-real-post` はworkflowに含めない

Actionsはこの作業では実行していない。初回運用時はGitHub Secrets設定を確認し、workflow logsにsecret値が出ていないことを確認する。

## Metrics / second account pilot note (2026-06-30)

`import_threads_metrics_manual.py` は、本番保存時に以下が必須。

```bash
python3 scripts/import_threads_metrics_manual.py \
  --result-id <result_id> \
  --views <数値> \
  --likes <数値> \
  --comments <数値> \
  --follows <数値> \
  --profile-clicks <数値> \
  --line-adds <数値> \
  --memo "<確認メモ>" \
  --use-sheets \
  --apply \
  --confirm-metrics
```

値なしdry-runはテンプレート表示のみで、`MEASURED` にはしない。

```bash
python3 scripts/import_threads_metrics_manual.py --result-id <result_id> --dry-run
```

`night_scout` の追加投稿は、このturnでは承認システム `out of credits` により未実行。次回は以下の順で1件のみ実施する。

```bash
python3 scripts/recover_production_sheets_threads_first.py --verify-only --json
python3 scripts/process_threads_queue.py --account-id night_scout --dry-run --max-posts 1
PUBLISH_ENABLED=true ALLOW_REAL_THREADS_POST=true python3 scripts/process_threads_queue.py --account-id night_scout --max-posts 1 --confirm-real-post
```

失敗時にretryしない。成功後は `posted_results` と `queue` を確認し、metricsは別途明示値で取り込む。
