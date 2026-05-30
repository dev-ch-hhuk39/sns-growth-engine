# 参考投稿収集 使い方ガイド

**最終更新**: 2026-05-30

---

## 概要

`scripts/collect_references.py` を使って X の参考投稿を収集し `reference_posts` タブに保存する。

現在は JSON 入力 / mock 入力 / dry-run に対応。X API 本番収集は Phase 2.10 本格実装後。

---

## JSON 入力モード

事前に収集した投稿を JSON ファイルで入力する。

```bash
# dry-run（Sheetsへ書かない）
python scripts/collect_references.py \
  --account-id night_scout \
  --platform x \
  --input-json fixtures/sample_x_posts.json \
  --dry-run

# 実Sheets へ書き込む
python scripts/collect_references.py \
  --account-id night_scout \
  --platform x \
  --input-json fixtures/sample_x_posts.json \
  --use-sheets \
  --test-write
```

### JSON フォーマット

`fixtures/sample_x_posts.json` を参照。最低限必要なフィールド:

```json
[
  {
    "post_id": "投稿ID",
    "post_url": "https://x.com/...",
    "account_handle": "@ハンドル名",
    "account_name": "表示名",
    "posted_at": "2026-05-28T10:00:00+09:00",
    "text": "投稿テキスト",
    "image_urls": [],
    "video_urls": [],
    "like_count": 100,
    "reply_count": 10,
    "repost_count": 20,
    "bookmark_count": 30,
    "impression_count": 5000
  }
]
```

---

## mock モード

ファイルなしでモックデータを生成して動作確認する。

```bash
python scripts/collect_references.py \
  --account-id night_scout \
  --platform x \
  --mock \
  --dry-run
```

---

## X API モード（未本番実装）

`--use-x-api` フラグで有効化する設計だが、現在は `NotImplementedError` を返す。

Phase 2.10 本格実装後に使用可能になる。

```bash
# 現在は実行不可（NotImplementedError）
python scripts/collect_references.py \
  --account-id night_scout \
  --use-x-api \
  --dry-run
```

---

## 安全ルール

- デフォルトは dry-run（`--dry-run` フラグが自動で ON）
- `--use-sheets` がない限り実 Sheets へ書き込まない
- `--test-write` がない限り実 Sheets へ書き込まない
- `--use-x-api` がない限り X API を呼ばない
- SNS 投稿は絶対にしない（PUBLISH_ENABLED=false が前提）
- queue タブへの積み込みは行わない

---

## ログ記録

`--use-sheets --test-write` 時は logs タブに以下を記録する:

- `operation`: `collect_references`
- `status`: `OK`
- `message`: 収集・正規化件数

---

## 重複対策

`post_id` が同一の場合は保存をスキップする（`save_reference_post` が False を返す）。

重複件数は `save_reference_posts()` の戻り値 `{"added": n, "skipped": n, "errors": n}` で確認できる。

---

## 今後のフェーズ

- **Phase 2.11**: `reference_post_analyzer.py` で performance_score を計算し `reference_post_scores` に書き込む
- **Phase 2.12**: `cloudinary_client.py` で画像・動画を Cloudinary に保存し `media_assets` に記録する
- **Phase 2.13**: `generation_planner.py` で 8:2 生成計画を `generation_jobs` に書き込む
