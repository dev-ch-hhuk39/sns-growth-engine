# Metrics Import Runbook

Date: 2026-06-24

## Purpose

Threads insights are imported manually with `scripts/import_threads_metrics_manual.py`.

This keeps the PDCA loop human-reviewed:

- `posted_results.metrics_status=MEASURED`
- `collected_at` updated
- `pdca_runs` appended
- `prompt_improvement_suggestions.status=WAITING_REVIEW`
- `learning_rules.active=false` remains unchanged
- no prompt/code auto rewrite

## Command

```bash
python3 scripts/import_threads_metrics_manual.py \
  --result-id <result_id> \
  --views 100 \
  --likes 5 \
  --comments 1 \
  --follows 0 \
  --profile-clicks 2 \
  --line-adds 0 \
  --memo "manual insights import"
```

Dry-run:

```bash
python3 scripts/import_threads_metrics_manual.py \
  --result-id <result_id> \
  --views 100 \
  --likes 5 \
  --comments 1 \
  --follows 0 \
  --profile-clicks 2 \
  --line-adds 0 \
  --memo "manual insights import" \
  --dry-run
```

Dry-run does not call `get_config()`, instantiate `SheetsClient`, or run `setup_all()`. It only validates numeric inputs and prints the fields that would be updated.

## Idempotency (2026-06-27)

`pdca_runs` / `prompt_improvement_suggestions` への追記は決定論的 id
（`pdca_metrics_<result_id>` / `sug_metrics_<result_id>`）を使う。
同じ `result_id` を再インポートしても、`row_exists()` ガードにより二重追記しない。

- 初回: `pdca_appended=true`, `suggestion_appended=true`
- 2回目以降: `pdca_appended=false`, `suggestion_appended=false`（メトリクス値の更新は行われる）

ER は純粋関数 `compute_engagement_rate(views, likes, comments)` で計算する
（`views<=0` のとき `0.0`、それ以外は `(likes+comments)/views` を小数4桁に丸め）。
実行時の JSON 出力に `er` / `pdca_appended` / `suggestion_appended` を含む。

## 次回キュー候補生成（generate_next_queue_from_metrics.py）

MEASURED な `posted_results` を ER 降順でランキングし、次回投稿候補を作る。

```bash
# 計画のみ（書き込みなし）
python3 scripts/generate_next_queue_from_metrics.py --account-id liver_manager --count 2
# 実生成（本番 Sheets 書き込み）
python3 scripts/generate_next_queue_from_metrics.py --account-id liver_manager --count 2 --apply --confirm-generate
```

安全保証:
- 生成 queue 行の status は `DRAFT`（worker の `ELIGIBLE_STATUSES`={WAITING_REVIEW, PLANNED} に含めない）。
  → `process_threads_queue.py` が自動投稿しない。
- beauty_account / x は対象外。改善提案は WAITING_REVIEW（auto_apply=false）。source priority は変更しない。

## Required Human Review

After import, review:

- `投稿結果`: `metrics_status=MEASURED`
- `PDCA実行履歴`: one manual metrics run（再インポートでは増えない）
- `改善提案`: `WAITING_REVIEW`
- `学習ルール`: `active=false`, `auto_apply=false`
- 次回候補（生成した場合）: `queue.status=DRAFT`（worker 非対象）であること
