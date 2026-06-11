# Post-Results Learning Loop

## 概要

実投稿後の成果データを学習サイクルへ戻す基盤。
外部APIからの自動取得は行わず、手動インポートまたはCSV/JSONから取り込む。

## アーキテクチャ

```
posted_results タブ
  ↓ analyze_post_results.py
PostResultAnalyzer（src/learning/post_result_analyzer.py）
  ↓ generate_learning_from_results.py
ImprovementSuggester（src/learning/improvement_suggester.py）
  ↓ status=WAITING_REVIEW で保存
prompt_improvement_suggestions タブ
  ↓ 人間が review_improvement_suggestions.py で承認
learning_rules タブ（active=false 初期値）
  ↓ 人間が approve_learning_rule.py で有効化
生成プロンプトに反映
```

## 安全制約

- learning_rules.active=true の**自動設定禁止**（人間承認が必須）
- prompt/code の**自動書き換え禁止**
- X API / Threads API からの直接取得禁止
- posted_results への本番投稿結果保存は投稿スクリプト経由のみ
- 全改善提案は status=WAITING_REVIEW で出力

## 1. データ取り込み（import_post_results.py）

```bash
# JSON からインポート（dry-run）
python scripts/import_post_results.py \
  --input tests/fixtures/sample_post_results_import.json \
  --dry-run

# CSV からインポート（dry-run）
python scripts/import_post_results.py \
  --input tests/fixtures/sample_post_results_import.csv \
  --dry-run

# Sheets へのテスト書き込み（fixture由来・is_test_data=true）
python scripts/import_post_results.py \
  --input tests/fixtures/sample_post_results_import.json \
  --use-sheets \
  --test-write
```

### 取り込みフォーマット

JSON:
```json
{
  "results": [
    {
      "result_id": "pr_001",
      "account_id": "night_scout",
      "platform": "x",
      "posted_at": "2025-06-01T09:00:00Z",
      "impressions": 1200,
      "likes": 48,
      "reposts": 12,
      "replies": 3,
      "profile_clicks": 5,
      "line_clicks": 2,
      "url_clicks": 8,
      "generation_mode": "video_clip_reference"
    }
  ]
}
```

CSV ヘッダー:
```
result_id,account_id,platform,posted_at,impressions,likes,reposts,replies,profile_clicks,line_clicks,url_clicks,generation_mode
```

## 2. 分析（analyze_post_results.py）

```bash
python scripts/analyze_post_results.py --account-id night_scout
python scripts/analyze_post_results.py --account-id night_scout --platform x --json
```

### 分析指標

**PV系（リーチ）**:
- impressions（表示回数）
- reposts（拡散）

**CV系（行動）**:
- likes（いいね）
- replies（返信）
- profile_clicks（プロフィールクリック）
- line_clicks（LINE誘導）
- url_clicks（URL クリック）

## 3. 改善提案生成（generate_learning_from_results.py）

```bash
# dry-run（常時安全）
python scripts/generate_learning_from_results.py \
  --account-id night_scout \
  --dry-run

# Sheets への書き込み（テスト用）
python scripts/generate_learning_from_results.py \
  --account-id night_scout \
  --use-sheets \
  --dry-run
```

全提案は `status=WAITING_REVIEW` で出力される。
`active=false` が保証される（自動 true 設定禁止）。

## 4. 改善提案のレビュー

```bash
# 提案一覧の確認
python scripts/review_improvement_suggestions.py --account-id night_scout

# 提案の承認/却下
python scripts/approve_learning_rule.py --suggestion-id {id} --approve
python scripts/approve_learning_rule.py --suggestion-id {id} --reject
```

## 5. forbidden 矛盾チェック

改善提案のテキストに `forbidden_keywords` / `forbidden_themes` が含まれる場合:

- `status=WAITING_REVIEW` で保存（自動 REJECT しない）
- `forbidden_conflict` フィールドに矛盾内容を記録
- `warn_message` に REJECT 推奨メッセージを記録
- 人間が確認して REJECT または修正

## 関連ファイル

- `src/learning/post_result_analyzer.py` - 分析ロジック
- `src/learning/improvement_suggester.py` - 改善提案生成
- `scripts/import_post_results.py` - データ取り込み
- `scripts/analyze_post_results.py` - 分析実行
- `scripts/generate_learning_from_results.py` - 提案生成
- `tests/fixtures/sample_post_results_import.json` - テストフィクスチャ
