# reference_posts スキーマ定義

**最終更新**: 2026-05-30

---

## 概要

X / Threads から収集した参考投稿を保存するタブ。本文模倣ではなく「勝ち要素」を抽出して再利用するための原材料。

---

## カラム定義

| カラム | 型 | 説明 | Phase 2.10 追加 |
|---|---|---|---|
| `id` | UUID | 内部ID（gspread UUID） | |
| `created_at` | ISO8601 | レコード作成日時 | |
| `account_id` | str | v2 アカウントID（night_scout / liver_manager） | |
| `platform` | str | 収集元プラットフォーム（x / threads） | |
| `post_url` | URL | 元投稿のURL | |
| `post_id` | str | プラットフォームの投稿ID（重複判定に使用） | |
| `title` | str | タイトル（分析後に付与） | |
| `text` | str | 投稿テキスト（整形後） | |
| `media_urls` | str | 画像・動画URL（`\|` 区切り） | |
| `likes` | int | いいね数 | |
| `reposts` | int | リポスト数 | |
| `impressions` | int | インプレッション数 | |
| `source_type` | str | 収集元（account_monitor / keyword_search） | |
| `author` | str | 投稿者の表示名 | |
| `published_at` | ISO8601 | 元投稿の投稿日時 | |
| `hook_type` | str | 書き出しパターン分類（Phase 2.11で付与） | |
| `extracted_hook` | str | フック文（書き出しテキスト） | |
| `extracted_pain` | str | ペインポイント抽出（Phase 2.11で付与） | |
| `extracted_desire` | str | 欲求抽出（Phase 2.11で付与） | |
| `reusable_pattern` | str | 再利用パターンメモ | |
| `imitation_risk` | str | 模倣リスク（low / medium / high / unknown） | |
| `status` | str | 処理状態（new / analyzed / used / rejected） | |
| `notes` | str | 備考 | |
| `original_text` | str | **Phase 2.10** 元投稿の生テキスト（text は整形後） | ✓ |
| `account_handle` | str | **Phase 2.10** @ハンドル名（author は表示名） | ✓ |
| `reply_count` | int | **Phase 2.10** 返信数 | ✓ |
| `bookmark_count` | int | **Phase 2.10** 保存数（Xブックマーク） | ✓ |
| `collected_at` | ISO8601 | **Phase 2.10** 収集日時 | ✓ |
| `keywords` | str | **Phase 2.10** 収集に使ったキーワード（`\|` 区切り） | ✓ |

---

## 重複判定

`post_id` を主キーとして重複判定を行う。

`post_id` が空の場合は `post_url` で判定する。

`SheetsClient.find_reference_post_by_post_id(post_id)` で重複確認後、`save_reference_post(post)` で保存する。

---

## 既存 X_autopost_yoru との対応

| 既存（RAW_HEADERS 47列） | reference_posts カラム |
|---|---|
| `post_id` | `post_id` |
| `post_url` | `post_url` |
| `account_name` | `author` |
| `account_id` | `account_id` |
| `posted_at` | `published_at` |
| `text` | `text` / `original_text` |
| `hook_text` | `extracted_hook` |
| `image_urls` / `video_urls` | `media_urls` |
| `like_count` | `likes` |
| `repost_count` | `reposts` |
| `impression_count` | `impressions` |
| `imitation_risk` | `imitation_risk` |
| `source_type` | `source_type` |
| `account_handle` | `account_handle` ← Phase 2.10 追加 |
| `reply_count` | `reply_count` ← Phase 2.10 追加 |
| `bookmark_count` | `bookmark_count` ← Phase 2.10 追加 |
