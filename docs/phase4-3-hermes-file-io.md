# Phase 4.3: Hermes向け export/import 実運用整備

## 概要

Hermes Agent（無料版・未インストール）との連携は **ファイル export/import** のみで行う。
Sheets直接編集・SNS投稿・コード自動変更は Hermes に渡さない。

## Export（4ファイル出力）

```bash
python scripts/export_learning_context.py \
  --account-id night_scout --output-dir exports/hermes
```

### 出力ファイル

| ファイル | 内容 |
|---|---|
| `weekly_growth_report_{account}_{date}.md` | 週次レポート（Markdown） |
| `performance_summary_{account}_{date}.json` | 投稿実績サマリー |
| `account_memory_snapshot_{account}_{date}.json` | アカウント記憶スナップショット |
| `improvement_context_{account}_{date}.json` | 改善提案コンテキスト |

### セキュリティ

- API キー・シークレットは `[REDACTED]` にマスク
- git commit 禁止（.gitignore に `exports/hermes/` を追加推奨）

## Import（提案受け取り）

### 標準パス

```
imports/hermes/improvement_suggestions.json
imports/hermes/suggestions_*.json
```

### インポート手順

```bash
# Hermes標準パスから自動検出
python scripts/import_improvement_suggestions.py --from-hermes --use-sheets

# 個別ファイル
python scripts/import_improvement_suggestions.py \
  --input imports/hermes/improvement_suggestions.json --use-sheets
```

### インポート時の保証

- 全提案は `status=WAITING_REVIEW` で保存
- `source=hermes` を維持
- `risk_level=high` の場合は `[WARN]` 表示
- `forbidden_themes` 矛盾 → `REJECT候補` として `[WARN]` + `risk_level=high` に格上げ
- `prompt/code` 自動変更なし
- Sheets直接編集なし
- SNS投稿なし

## Hermes連携フロー（全体像）

```
export_learning_context.py
        ↓
  exports/hermes/ ← Hermes が読む（手動渡し）
        ↓
  Hermes が提案生成
        ↓
  imports/hermes/improvement_suggestions.json ← Hermes が書く（手動受け取り）
        ↓
  import_improvement_suggestions.py
        ↓
  prompt_improvement_suggestions タブ (WAITING_REVIEW)
        ↓
  review_improvement_suggestions.py （人間確認）
        ↓
  approve_learning_rule.py → APPROVED
        ↓
  activate_learning_rule.py → learning_rules (active=false)
        ↓
  activate_learning_rule.py --confirm-activate → active=true（最終人間判断）
```
