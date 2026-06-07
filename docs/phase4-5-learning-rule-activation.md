# Phase 4.5: prompt改善案 → learning_rules 反映 安全化

## 概要

改善提案（`prompt_improvement_suggestions`）から `learning_rules` への変換フローを安全化する。

## フロー

```
提案（APPROVED）
  ↓ activate_learning_rule.py --create-rule
learning_rules (active=false)
  ↓ activate_learning_rule.py --confirm-activate
learning_rules (active=true)  ← 最終人間判断
```

## コマンド

```bash
# APPROVED 提案から learning_rule 候補を作成（active=false）
python scripts/activate_learning_rule.py \
  --suggestion-id sug-XXXXXXXX --create-rule

# dry-run 確認
python scripts/activate_learning_rule.py \
  --suggestion-id sug-XXXXXXXX

# learning_rule を active=true にする（--confirm-activate 必須）
python scripts/activate_learning_rule.py \
  --rule-id rule-XXXXXXXX --confirm-activate

# Sheets書き込みあり
python scripts/activate_learning_rule.py \
  --rule-id rule-XXXXXXXX --confirm-activate --use-sheets
```

## 安全ガード

### activate 禁止パターン

| アカウント | 禁止パターン |
|---|---|
| `night_scout` | 代理店、パートナー募集、情報商材、スカウト代理店、組織的に稼ぐ |
| `liver_manager` | 代理店、情報商材、誰でも稼げる、副業で稼ぐ、ネットワーク |

### 禁止事項

- `active=true` の自動設定
- `--confirm-activate` なし activation
- `forbidden_themes` / `forbidden_keywords` 矛盾ルールの activate
- `night_scout` に代理店向けルール復活
- `liver_manager` に怪しい副業訴求ルール
- `prompt/code` の自動変更

## activation ログ

全 activate 操作は `logs/learning_rule_activations.log` に記録される。

```
2026-06-07T00:00:00+00:00 | RULE_ACTIVATED | rule_id=rule-XXXXXXXX | account_id=night_scout
```

## 整合性チェック

```bash
python scripts/check_learning_integrity.py --account-id night_scout
```
