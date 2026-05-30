# Phase 2.10: X Reference Collector 移植

**実施日**: 2026-05-30

---

## 概要

`X_autopost_yoru/x_collect_posts.py` の設計を v2 に移植した。

X API 本番収集はまだ実行しない。JSON 入力 / mock 入力 / dry-run で動作確認できる状態まで実装。

---

## 実装ファイル

| ファイル | 役割 |
|---|---|
| `src/collectors/x_reference_collector.py` | 正規化ロジック・X API クライアントスタブ |
| `scripts/collect_references.py` | 収集 CLI |
| `fixtures/sample_x_posts.json` | テスト用ダミーデータ（3件） |
| `scripts/test_phase29_210.py` | Phase 2.9/2.10 テスト（67テスト） |

---

## 入力対応フォーマット

`normalize_post()` は以下の形式を自動的に検出して変換する。

- X API v2 風 JSON（tweet オブジェクト）
- 外部コレクター（AgentReach 等）が吐く JSON
- 既存 `x_collect_posts.py` が生成する JSON
- `public_metrics` ネストオブジェクト対応

### 対応フィールドマッピング

| 入力フィールド | reference_posts カラム |
|---|---|
| `post_id` / `id` / `tweet_id` | `post_id` |
| `post_url` / `url` | `post_url` |
| `account_handle` / `user` | `account_handle` |
| `account_name` / `name` | `author` |
| `posted_at` / `created_at` | `published_at` |
| `text` / `full_text` | `text` / `original_text` |
| `like_count` / `likes` | `likes` |
| `reply_count` / `replies` | `reply_count` |
| `repost_count` / `retweet_count` | `reposts` |
| `bookmark_count` / `bookmarks` | `bookmark_count` |
| `impression_count` / `views` | `impressions` |
| `image_urls` | `media_urls`（一部） |
| `video_urls` | `media_urls`（一部） |
| `matched_keywords` / `keywords` | `keywords` |
| `hook_text` / `extracted_hook` | `extracted_hook` |

---

## collect_references.py の使い方

```bash
# JSON入力（dry-run・Sheetsへ書かない）
python scripts/collect_references.py \
  --account-id night_scout \
  --platform x \
  --input-json fixtures/sample_x_posts.json \
  --dry-run

# モック入力（ファイル不要）
python scripts/collect_references.py \
  --account-id night_scout \
  --platform x \
  --mock \
  --dry-run

# 実Sheets test-write
python scripts/collect_references.py \
  --account-id night_scout \
  --platform x \
  --input-json fixtures/sample_x_posts.json \
  --use-sheets \
  --test-write
```

## 安全フラグ

| フラグ | 説明 |
|---|---|
| `--dry-run` | Sheetsへの書き込みをスキップ（デフォルト ON） |
| `--use-sheets` | 実SheetsClient を使用（--test-write と組み合わせる） |
| `--test-write` | 実Sheetsへ書き込みを実行 |
| `--use-x-api` | X APIを使って収集（現在は `NotImplementedError`） |

---

## X API 本番収集について

`fetch_account_posts()` / `fetch_keyword_posts()` は実装済みスタブ。

`--use-x-api` フラグなしでは呼ばれない。Phase 2.10 本格実装（予定）まで `NotImplementedError` を返す。

---

## 既存 X_autopost_yoru との対応

| 既存関数 | v2 相当 |
|---|---|
| `normalize_post()` | `normalize_post()` ✓ |
| `fetch_account_posts()` | `fetch_account_posts()` スタブ |
| `upsert_raw_sheet()` | `SheetsClient.save_reference_post()` |
| `load_config()` | `config_loader.get_config()` |

---

## 次のフェーズ

- Phase 2.11: `reference_post_analyzer.py` で performance_score を計算し `reference_post_scores` に書き込む
- Phase 2.12: `cloudinary_client.py` で media_assets に保存する
