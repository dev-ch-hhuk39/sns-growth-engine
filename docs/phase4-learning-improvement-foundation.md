# Phase 4.0: Learning / Self-Improvement Foundation

## 概要

SNS 自動投稿システム v2 の自己改善基盤。パフォーマンスデータを分析して
改善提案を生成し、人間が承認後にシステムへ反映するフローを構築した。

---

## 追加ファイル

### src/learning/

| ファイル | 説明 |
|---------|------|
| `__init__.py` | learning パッケージ |
| `performance_analyzer.py` | パフォーマンスメトリクス算出 |
| `improvement_suggester.py` | 改善提案生成 |

### scripts/

| ファイル | 説明 |
|---------|------|
| `export_learning_context.py` | Sheets → JSON エクスポート |
| `import_improvement_suggestions.py` | JSON → Sheets インポート（WAITING_REVIEW） |
| `review_improvement_suggestions.py` | WAITING_REVIEW 一覧表示（読み取り専用） |
| `approve_learning_rule.py` | 提案・ルールの承認（--confirm-approve 必須） |
| `check_learning_integrity.py` | 学習システム整合性チェック |

---

## Sheets タブ追加

### prompt_improvement_suggestions

| 列 | 説明 |
|----|----|
| suggestion_id | sug-XXXXXXXX |
| source | hermes / manual / performance_analyzer |
| suggestion_type | prompt_change / rule_addition / strategy_change |
| status | **WAITING_REVIEW** / APPROVED / REJECTED |
| reviewed_by | human（自動承認は禁止） |

---

## 運用フロー

```bash
# 1. 学習コンテキストのエクスポート
python scripts/export_learning_context.py --account-id night_scout

# 2. PerformanceAnalyzer で提案生成（または Hermes からインポート）
python scripts/import_improvement_suggestions.py \
  --input tests/fixtures/sample_improvement_suggestions.json

# 3. 提案のレビュー（読み取り専用）
python scripts/review_improvement_suggestions.py --account-id night_scout

# 4. 承認
python scripts/approve_learning_rule.py \
  --suggestion-id sug-XXXXXXXX \
  --confirm-approve \
  --use-sheets

# 5. 整合性チェック
python scripts/check_learning_integrity.py --account-id night_scout
```

---

## 安全ガード

| 禁止事項 | 実装保証 |
|---------|---------|
| active=true の自動設定 | ImprovementSuggester は active フィールドを出力しない |
| status=APPROVED の自動インポート | import スクリプトがバリデーションでブロック |
| --confirm-approve なし承認 | approve_learning_rule.py がドライランで終了 |
| prompt / code の自動書き換え | 提案のみ生成・承認フローのみ |

---

## Phase 4.1 追加

- `scripts/approve_learning_rule.py` (learning_rule の active=true 設定)
- `scripts/check_learning_integrity.py` (整合性チェック)
- `check_pipeline_integrity.py` への learning integrity 拡張

---

## テスト

```bash
python scripts/test_phase4_learning.py
# 期待: PASS=N WARN=0 FAIL=0
```

---

## 参考

- 全体アーキテクチャ: `docs/self-improvement-architecture.md`
- Hermes Agent 設計: `docs/hermes-agent-integration-plan.md`
- Headroom セットアップ: `docs/headroom-production-setup.md`
