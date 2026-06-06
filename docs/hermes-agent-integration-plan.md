# Hermes Agent 導入設計（Phase HERMES-0）

## 概要

Hermes Agent は SNS 自動投稿システムの長期記憶・自己改善エージェントです。
**設計のみ（Phase HERMES-0）。実インストールは Phase HERMES-1 以降で実施します。**

---

## 設計原則

| 原則 | 内容 |
|------|------|
| ファイルベース I/O のみ | Sheets への直接書き込み禁止 |
| SNS 投稿権限なし | 本番投稿は禁止 |
| 提案は全件 WAITING_REVIEW | 人間承認なしの自動適用禁止 |
| 読み取り専用 | export_learning_context.py 経由のデータのみ |

---

## アーキテクチャ

```
[Sheets / Pipeline]
        ↓ (読み取り専用)
export_learning_context.py
        ↓
exports/hermes/learning_context_YYYYMMDD.json
        ↓ (Hermes が分析)
Hermes Agent（ファイルベース分析）
        ↓
imports/hermes/suggestions_YYYYMMDD.json
        ↓
import_improvement_suggestions.py
        ↓ (WAITING_REVIEW で保存)
[prompt_improvement_suggestions タブ]
        ↓ (人間レビュー)
review_improvement_suggestions.py
        ↓ (承認)
approve_learning_rule.py --confirm-approve
        ↓
[active=true / status=APPROVED]
```

---

## ファイル構成

### エクスポート先（Hermes への入力）

```
exports/hermes/
  learning_context_{account_id}_{YYYYMMDD}.json    # export_learning_context.py 出力
```

### インポート元（Hermes からの出力）

```
imports/hermes/
  suggestions_{YYYYMMDD}.json    # Hermes が生成する提案ファイル
  weekly_report_{YYYYMMDD}.md    # Hermes 週次レポート（optional）
```

---

## データフォーマット

### 提案ファイル（imports/hermes/suggestions_YYYYMMDD.json）

```json
{
  "suggestions": [
    {
      "suggestion_id": "sug-XXXXXXXX",
      "account_id": "night_scout",
      "source": "hermes",
      "suggestion_type": "prompt_change",
      "current_behavior": "...",
      "suggested_change": "...",
      "reason": "...",
      "expected_impact": "...",
      "priority": "high",
      "status": "WAITING_REVIEW"
    }
  ]
}
```

---

## 禁止事項

```
Hermes Agent に Sheets 編集権限を付与           → 人間レビューバイパス防止
Hermes Agent に SNS 投稿権限を付与             → 誤投稿防止
active=true の自動設定                          → 承認なし適用禁止
status=APPROVED の自動設定                      → 同上
GitHub Actions での自動実行                     → 誤実行防止
prompt / code の自動書き換え                    → システム安全性確保
```

---

## Phase HERMES-1 以降の計画

Phase HERMES-0（現在）: 設計・ドキュメントのみ  
Phase HERMES-1: ファイルベース分析スクリプトの実装  
Phase HERMES-2: Headroom 経由での LLM 分析統合  
Phase HERMES-3: 週次レポート自動生成（要人間レビュー）

---

## 参考

- 自己改善アーキテクチャ全体: `docs/self-improvement-architecture.md`
- Learning foundation: `docs/phase4-learning-improvement-foundation.md`
- Headroom setup: `docs/headroom-production-setup.md`
