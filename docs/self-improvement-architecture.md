# Self-Improvement Architecture（Phase 4.0 / HERMES-0）

## 概要

SNS 自動投稿システム v2 の自己改善基盤のアーキテクチャ設計書。
パフォーマンスデータから改善提案を生成し、人間が承認後にシステムへ反映するフローを定義する。

---

## 設計原則

1. **人間中心の承認フロー**: 全改善提案は `WAITING_REVIEW` → 人間承認 → `APPROVED` の順
2. **ファイルベース I/O**: Hermes Agent はファイルのみ読み書き（Sheets 直接アクセス禁止）
3. **段階的適用**: `active=true` の自動設定は禁止、`approve_learning_rule.py` 経由のみ
4. **監査可能性**: 全提案は `reviewed_by`, `reviewed_at` で追跡可能

---

## コンポーネント構成

```
┌─────────────────────────────────────────────────────────────────┐
│  Data Layer (Google Sheets)                                       │
│   posted_results / queue / video_clip_candidates                  │
│   learning_rules / prompt_improvement_suggestions                 │
└─────────────────────────────────────────────────────────────────┘
              ↑ read only          ↑ write (WAITING_REVIEW only)
┌─────────────────────┐   ┌──────────────────────────────────────┐
│  PerformanceAnalyzer │   │  import_improvement_suggestions.py   │
│  (src/learning/)     │   │  (status=WAITING_REVIEW で保存)      │
└─────────────────────┘   └──────────────────────────────────────┘
              ↓                           ↑
┌─────────────────────┐   ┌──────────────────────────────────────┐
│  ImprovementSuggester│   │  imports/hermes/suggestions_*.json   │
│  (src/learning/)     │   │  (Hermes Agent が生成)               │
└─────────────────────┘   └──────────────────────────────────────┘
              ↓ (file)              ↑ (file)
┌─────────────────────────────────────────────────────────────────┐
│  exports/hermes/learning_context_*.json                           │
│  (export_learning_context.py が生成)                              │
└─────────────────────────────────────────────────────────────────┘
              ↓ (オプション: Hermes Agent が読む)
┌─────────────────────────────────────────────────────────────────┐
│  Hermes Agent (Phase HERMES-1 以降で実装)                         │
│   - LLM 分析（Headroom proxy 経由）                               │
│   - 週次レポート生成                                               │
│   - 提案ファイル生成 → imports/hermes/                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 人間レビューフロー

```
1. export_learning_context.py --account-id <ID>
   → exports/hermes/learning_context_<ID>_YYYYMMDD.json

2. (Hermes Agent または PerformanceAnalyzer が分析)
   → imports/hermes/suggestions_YYYYMMDD.json

3. import_improvement_suggestions.py --input FILE.json --use-sheets
   → prompt_improvement_suggestions タブ（status=WAITING_REVIEW）

4. review_improvement_suggestions.py --account-id <ID>
   → WAITING_REVIEW 一覧の表示

5. approve_learning_rule.py --suggestion-id <ID> --confirm-approve
   → status=APPROVED, reviewed_by=human
```

---

## データスキーマ

### prompt_improvement_suggestions タブ

| 列 | 型 | 説明 |
|----|----|------|
| suggestion_id | str | sug-XXXXXXXX 形式 |
| account_id | str | night_scout / liver_manager |
| source | enum | hermes / manual / performance_analyzer |
| suggestion_type | enum | prompt_change / rule_addition / strategy_change |
| status | enum | **WAITING_REVIEW** / APPROVED / REJECTED |
| reviewed_by | str | human（自動承認は禁止） |

---

## 安全ガード一覧

| ガード | 実装箇所 |
|--------|---------|
| active=true 自動設定禁止 | `ImprovementSuggester` （active フィールド不出力） |
| APPROVED 自動設定禁止 | `import_improvement_suggestions.py` バリデーション |
| --confirm-approve 必須 | `approve_learning_rule.py` |
| Sheets 直接書き込み禁止（Hermes） | 設計方針（ファイルベース I/O のみ） |
| 長期 WAITING_REVIEW 検出 | `check_learning_integrity.py`（7日以上で WARN） |

---

## 関連ファイル

- `src/learning/performance_analyzer.py` - メトリクス算出
- `src/learning/improvement_suggester.py` - 提案生成
- `scripts/export_learning_context.py` - エクスポート
- `scripts/import_improvement_suggestions.py` - インポート
- `scripts/review_improvement_suggestions.py` - レビュー表示
- `scripts/approve_learning_rule.py` - 承認
- `scripts/check_learning_integrity.py` - 整合性チェック
- `docs/hermes-agent-integration-plan.md` - Hermes 設計
