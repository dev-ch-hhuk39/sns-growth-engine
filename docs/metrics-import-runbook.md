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

## Required Human Review

After import, review:

- `投稿結果`: `metrics_status=MEASURED`
- `PDCA実行履歴`: one manual metrics run
- `改善提案`: `WAITING_REVIEW`
- `学習ルール`: `active=false`, `auto_apply=false`
