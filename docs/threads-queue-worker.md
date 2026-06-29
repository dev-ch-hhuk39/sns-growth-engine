# Threads Queue Worker

Date: 2026-06-29 (最終更新 — READY 承認モデル必須化)
Created: 2026-06-24

## Purpose

`scripts/process_threads_queue.py` processes Google Sheets `投稿キュー` rows for Threads-first operation.

It is intentionally narrow:

- account: `night_scout` or `liver_manager`
- platform: `threads`
- eligible status: **`READY` のみ**（`ELIGIBLE_STATUSES = {"READY"}`）
- default batch: 1 row
- hard cap: 2 rows
- `beauty_account`: blocked
- X rows: ignored

## Status モデル（READY 承認モデル）

投稿対象は **`READY` のみ**。それ以外は投稿対象にしない。

| status | 意味 | 投稿可否 |
|--------|------|----------|
| `WAITING_REVIEW` | レビュー待ち（生成系CLIの既定出力 / 人間レビュー前） | ✗ |
| `READY` | 人間が `approve_queue.py` で承認済み | ✓ worker 対象 |
| `PROCESSING` | worker 処理中（一時状態） | — |
| `POSTED` | 投稿完了 | ✗（再投稿しない） |
| `DRAFT` | 生成 / PDCA 候補 | ✗ |
| `PLANNED` | 計画段階（投稿対象外） | ✗ |
| `REJECTED` | レビューで却下 | ✗ |

状態遷移: `WAITING_REVIEW → READY → PROCESSING → POSTED`

- `READY` への昇格は **`approve_queue.py` 経由でのみ** 行う。生成系CLI（refill / ideas / metrics 候補）は直接 `READY` を書かない（既定は `WAITING_REVIEW` / `DRAFT`）。
- `approve_queue.py` は status を `READY` か `REJECTED` にのみ変更し、`generation_mode` を保持したまま logs に `queue_approved` 証跡を残す。

```bash
# 一覧確認（読み取り専用）
python3 scripts/approve_queue.py --account-id night_scout --status WAITING_REVIEW --list
# WAITING_REVIEW → READY へ昇格（人間承認）。--approve は READY 変更のショートカット
python3 scripts/approve_queue.py --queue-id <id> --approve --reason "<理由>"
# 却下（REJECTED）
python3 scripts/approve_queue.py --queue-id <id> --reject --reason "<理由>"
```

`--status` に指定できる値は `READY` / `REJECTED` のみ（`ALLOWED_NEW_STATUSES`）。`--reason` は変更時必須。`--dry-run` では Sheets を変更せず logs にも証跡を残さない。

## Safety Gates

Real posting requires all of the following:

```bash
PUBLISH_ENABLED=true
ALLOW_REAL_THREADS_POST=true
python3 scripts/process_threads_queue.py --account-id night_scout --confirm-real-post --max-posts 1
```

The worker always performs a Threads publisher dry-run before real posting.

## True Dry-Run Definition

`--dry-run` is read-only:

- no `client.setup_all()`
- no tab creation
- no header addition
- no queue status update
- no logs append
- no `posted_results` append
- no `pdca_runs` / `prompt_improvement_suggestions` append
- no fallback JSON creation

The CLI prints `read_only=true` in dry-run outcomes.

Duplicate guards block:

- same `queue_id` already in `posted_results`
- same `derivative_id`
- same `draft_id` already `POSTED` or `RECOVERED`
- same `posted_text` for the same account/platform already `POSTED`

## Commands

```bash
python3 scripts/process_threads_queue.py --account-id night_scout --dry-run
python3 scripts/process_threads_queue.py --account-id liver_manager --dry-run
```

Real mode:

```bash
PUBLISH_ENABLED=true ALLOW_REAL_THREADS_POST=true \
python3 scripts/process_threads_queue.py --account-id night_scout --confirm-real-post --max-posts 1
```

## Failure Handling

- post failure: queue row becomes `FAILED`; no immediate retry
- duplicate: queue row becomes `DUPLICATE_BLOCKED` in real mode
- posted_results save failure after a successful post: queue row becomes `POSTED_SAVE_FAILED`, fallback JSON is written to `output/posted_results_fallback/`, and the row must not be reposted

## GitHub Actions

`.github/workflows/threads-queue-worker.yml` is manual-only (`workflow_dispatch`).

It runs:

1. **Repair posted_results integrity** (`repair_posted_results_integrity.py --apply`)
2. Sheets verify before processing
3. queue worker dry-run
4. process queue only if `mode=real_post` and `confirm_real_post=true`
5. **Sheets verify after processing** — `mode=real_post` のみ実行（`if: mode == 'real_post'`）。dry_run はSheets変更なしのため skip。sleep 60 を前置して 429 を回避。
6. **Upload fallback artifact** (`output/posted_results_fallback/`) — 実投稿後 Sheets 保存が失敗した場合の fallback JSON を Actions artifact として 30 日保存 (`if: always()`)

No schedule is configured.

## Sheets 429 対策

`process_threads_queue.py` の `append_row` / `update_row` は以下の対策済み:

- **ヘッダーキャッシュ**: `ws.row_values(1)` はセッション内で1回のみ呼ぶ。
- **指数バックオフ**: 429 発生時は 5s / 15s / 30s で最大 4 回リトライ。
- **setup_all 削除**: real_post モードで `client.setup_all()` を呼ばない（タブは初期化済み前提）。

## 孤児投稿の復旧

Threads 投稿は成功したが Sheets 保存が失敗した場合 (`POSTED_SAVE_FAILED` / `PROCESSING` 放置):

```bash
# 状況確認（dry-run）
python3 scripts/recover_orphan_threads_post.py \\
    --account-id night_scout \\
    --queue-id <queue_id> \\
    --skip-api-lookup

# 外部投稿IDが分かっている場合
python3 scripts/recover_orphan_threads_post.py \\
    --account-id night_scout \\
    --queue-id <queue_id> \\
    --external-post-id <id> \\
    --post-url "https://www.threads.net/..." \\
    --apply

# 外部投稿IDなし（Threads API ではテキスト一致探索）
python3 scripts/recover_orphan_threads_post.py \\
    --account-id night_scout \\
    --queue-id <queue_id> \\
    --apply
```

復旧後: posted_results に `status=RECOVERED` 行が追加され、queue は `status=POSTED` に更新される。

## Queue 件数の FAIL / WARN 設計

| 件数 | 動作 |
|------|------|
| 0 | `queue_night_scout_min1` or `queue_liver_manager_min1` = False → FAIL |
| 1〜2 | check = True（PASS）+ `warning_list` に `_low` 追記 + `refill_needed_accounts` に追加 |
| 3以上 | check = True、警告なし |

- `REFILL_THRESHOLD = 3`
- WARN だけでは `failed=0` のまま → GitHub Actions は exit 0 で通過する
- night_scout を投稿消費後 queue が 1〜2 に減っても FAIL にならない

## GitHub Actions Dry-Run Result

2026-06-26 (**最新・成功**):

- run `28212477795` (night_scout): **success** — verification_passed=33 failed=0, status=DRY_RUN ✓
- run `28212482318` (liver_manager): **success** — verification_passed=33 failed=0, status=DRY_RUN ✓

2026-06-25 (失敗履歴):

- run `28136692522`, `28136764181`: Sheets secrets が Actions に未登録のため失敗
- run `28152571068` (night_scout): success
- run `28152572576` (liver_manager): verify-after で 429 → sleep 20 では不足だったため失敗
- run `28212294485`, `28212291830`: sleep 20 でも 429 が継続 → dry_run では verify-after を skip する設計に変更

Required Actions secrets:

- `SNS_MASTER_SHEET_ID` or `SPREADSHEET_ID`
- `SA_JSON_BASE64` or `GCP_SA_JSON_BASE64`
- account-specific Threads secrets for night/liver

Run command:

```bash
gh workflow run threads-queue-worker.yml \
  --repo dev-ch-hhuk39/sns-growth-engine \
  -f account_id=night_scout \
  -f mode=dry_run \
  -f max_posts=1 \
  -f confirm_real_post=false
```
