# source_account_collector

指定アカウントの投稿を収集し、伸びている投稿を reference_posts に登録する（Phase 7.B）。

## 概要

- 実X API / 実Threads API 呼び出し禁止
- Scraping 禁止・規約違反取得禁止
- 手動JSON / CSV 投入で運用可能
- バズ判定（エンゲージメント率 / アカウント平均比）
- rights_status=unknown → `WAITING_REVIEW`

## 収集フロー

```
手動JSON/CSV → normalize_source_post() → compute_engagement_rate() → buzz判定 → select_top_posts() → reference_posts
```

## バズ判定基準

- `engagement_rate >= min_engagement_rate`
- または `likes >= avg_likes × 2.0`
- または `views >= avg_views × 2.0`

## 使い方

```bash
# JSONファイルから収集
python scripts/collect_source_account_posts.py \
  --account-id night_scout --source-platform x \
  --input-json tests/fixtures/sample_source_account_posts.json \
  --top-n 5 --dry-run

# CSVから収集
python scripts/collect_source_account_posts.py \
  --account-id night_scout --source-platform x \
  --input-csv path/to/posts.csv --top-n 10 --dry-run
```

## reference_posts スキーマ

| フィールド | 説明 |
|-----------|------|
| reference_post_id | `src_{platform}_{post_id}` |
| account_id | 自社アカウントID |
| source_platform | x / threads / tiktok / youtube_shorts |
| source_account | 元アカウント handle |
| engagement_rate | (likes+reposts+replies) / views |
| rights_status | unknown → WAITING_REVIEW |
| reuse_policy | reference_only（デフォルト） |
| buzz | バズ判定結果 |

## 安全ルール

- 実API呼び出しなし
- Scraping なし
- rights_status=unknown は常に WAITING_REVIEW
