# Phase 4.2: Learning改善提案 レビュー/承認フロー強化

## 概要

`prompt_improvement_suggestions` タブの提案を効率的にレビュー・承認するためのワークフロー。

## ステータス定義

| ステータス | 説明 |
|---|---|
| `WAITING_REVIEW` | レビュー待ち（インポート直後のデフォルト） |
| `APPROVED` | 人間が承認済み（learning_rules 候補化可能） |
| `REJECTED` | 棄却 |
| `IMPORTED` | Sheetsへのインポート完了 |
| `CONVERTED_TO_RULE` | learning_rules に変換済み |

## フィルタオプション

```bash
# account_id でフィルタ
python scripts/review_improvement_suggestions.py --account-id night_scout

# ステータスでフィルタ
python scripts/review_improvement_suggestions.py --status WAITING_REVIEW

# risk_level でフィルタ
python scripts/review_improvement_suggestions.py --risk-level high

# 複合フィルタ
python scripts/review_improvement_suggestions.py \
  --account-id night_scout --status WAITING_REVIEW --risk-level high
```

## forbidden_themes / forbidden_keywords 矛盾検出

提案テキストが `seeds.py` の以下と矛盾する場合は `[WARN REJECT候補]` を表示：

- `ACCOUNT_FORBIDDEN_KEYWORDS`
- `ACCOUNT_FORBIDDEN_THEMES`

### night_scout の禁止テーマ

- 代理店募集・紹介者募集
- スカウト業界のビジネス解説
- 情報商材型の稼ぎ方訴求

### liver_manager の禁止テーマ

- 代理店募集
- 情報商材的な副業訴求

## 承認フロー

```bash
# 1. レビュー表示（read-only）
python scripts/review_improvement_suggestions.py --account-id night_scout

# 2. 個別承認（--confirm-approve 必須）
python scripts/approve_learning_rule.py \
  --suggestion-id sug-XXXXXXXX --confirm-approve

# 3. learning_rules 候補作成（active=false）
python scripts/activate_learning_rule.py \
  --suggestion-id sug-XXXXXXXX --create-rule

# 4. learning_rule を active=true にする（--confirm-activate 必須）
python scripts/activate_learning_rule.py \
  --rule-id rule-XXXXXXXX --confirm-activate
```

## 安全ガード

- `--confirm-approve` なし → dry-run で終了
- `learning_rules` は必ず `active=false` で作成
- `active=true` への変更は `activate_learning_rule.py` 経由のみ
- `forbidden_themes` と矛盾するルールは `activate` 不可
- `prompt/code` の自動変更禁止

## 整合性チェック

```bash
python scripts/check_learning_integrity.py --account-id night_scout
```
