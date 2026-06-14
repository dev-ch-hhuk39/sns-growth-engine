# Source-to-Post Pipeline（Phase 11）

## 概要

`src/orchestrators/source_to_post_orchestrator.py` が実装する 8 ステップのパイプライン。

Source Account からポストを取得し、バズスコアリング、ビデオ理解、テキスト生成、プリフライトチェック、PDCA候補生成までを一連で処理する。

## パイプライン構成

```
Step 1: fetch         → Source から RawSourceItem 取得
Step 2: buzz_score    → バズスコアリング
Step 3: reference_posts → 参照投稿リスト構築
Step 4: media_plan    → VideoUnderstanding（文字起こし・クリップ計画）
Step 5: generation    → OriginalHypothesisGenerator / VideoReferenceGenerator
Step 6: preflight     → 安全チェック（beauty_account / confirm_post）
Step 7: publish_plan  → PublishResult 構築（干渉なし）
Step 8: pdca_candidates → PDCA 候補リスト生成
```

## 安全ゲート

| フラグ | 未設定時の動作 |
|---|---|
| confirm_fetch=False | Step 1 が BLOCKED |
| confirm_download=False | Step 4 は plan_only |
| confirm_post=False | Step 6 preflight=BLOCKED、Step 7 は publish_plan のみ |
| is_beauty=True | Step 6 preflight=BLOCKED、Step 5 は WAITING_REVIEW |

## 使い方（mock + dry_run）

```bash
python scripts/run_source_to_post_pipeline.py \
  --account-id night_scout \
  --platform x \
  --source-platform youtube \
  --mock \
  --dry-run
```

## Python API

```python
from src.orchestrators.source_to_post_orchestrator import run_pipeline

result = run_pipeline(
    account_id="night_scout",
    platform="x",
    source_platform="youtube",
    mock=True,
    dry_run=True,
)
print(result["status"])          # OK / WAITING_REVIEW / BLOCKED
print(result["safety"])          # {"no_real_post": True, "no_real_download": True, ...}
print(result["summary"])         # {"fetched_items": 3, "draft_count": 2, ...}
print(result["blocked_reasons"]) # []
```

## 返り値の主要フィールド

| フィールド | 型 | 説明 |
|---|---|---|
| run_id | str | 実行ID |
| account_id | str | 対象アカウント |
| status | str | OK / WAITING_REVIEW / BLOCKED |
| is_beauty | bool | beauty_account フラグ |
| steps | dict | 各ステップの実行結果 |
| safety | dict | 安全確認フラグ群 |
| summary | dict | 件数サマリ |
| blocked_reasons | list | ブロック理由リスト |
| pdca_candidates | list | PDCA 改善候補 |

## 本番利用時の注意

- `confirm_fetch=True` + `--confirm-fetch` フラグが必要
- `confirm_post=True` は実投稿を承認する操作（慎重に）
- `PUBLISH_ENABLED=true` は環境変数で明示的に設定する
- `beauty_account` は常に draft_only（BLOCKED）
