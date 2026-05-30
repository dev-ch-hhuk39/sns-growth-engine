# media_assets スキーマ仕様

**最終更新**: 2026-05-30

---

## 概要

`reference_posts` から抽出したメディア（画像・動画）を管理するタブ。
Cloudinaryへのアップロード状況・再利用リスクを追跡する。

---

## カラム一覧

| カラム | 説明 |
|---|---|
| `media_id` | UUID（自動生成） |
| `account_id` | v2 アカウントID |
| `reference_post_id` | reference_posts.id への外部参照 |
| `source_platform` | 収集元プラットフォーム（x, threads, etc.） |
| `source_post_url` | 収集元投稿URL |
| `original_media_url` | 元のメディアURL（参考投稿のURL） |
| `storage_provider` | ストレージ先（`cloudinary` / `none` / `dry_run`） |
| `storage_url` | Cloudinaryの secure_url（dry-run時は空文字） |
| `cloudinary_public_id` | Cloudinary public_id |
| `media_type` | メディア種別（`image` / `video` / `gif` / `unknown`） |
| `mime_type` | MIMEタイプ（例: `image/jpeg`, `video/mp4`） |
| `width` | 画像幅（px） |
| `height` | 画像高さ（px） |
| `duration` | 動画長（秒） |
| `reuse_status` | 再利用ステータス（`reference_only` / `approved` / `review` / `rejected`） |
| `media_reuse_risk` | 再利用リスク（`low` / `medium` / `high` / `unknown`） |
| `imitation_risk` | 模倣リスク（`low` / `medium` / `high`） |
| `downloaded_at` | ダウンロード日時（ISO8601） |
| `uploaded_at` | Cloudinaryアップロード日時（ISO8601） |
| `used_count` | 投稿に使用した回数 |
| `notes` | メモ |

---

## ユニークキー

`reference_post_id + original_media_url` の組み合わせでアップサートする。
1件の投稿に複数のメディアURLがある場合、それぞれ別行として保存する。

---

## reuse_status の値

| 値 | 意味 |
|---|---|
| `reference_only` | 参考閲覧のみ（デフォルト）。そのまま投稿に使用しない。 |
| `approved` | 再利用可（自作・権利クリア済み） |
| `review` | 再利用要審査 |
| `rejected` | 再利用不可 |

---

## media_reuse_risk の値

| 値 | 意味 |
|---|---|
| `low` | 再利用リスク低（公式素材・自作等） |
| `medium` | 再利用リスク中（要確認） |
| `high` | 再利用リスク高（他者コンテンツの可能性大） |
| `unknown` | 判定不明 |

---

## storage_provider の値

| 値 | 意味 |
|---|---|
| `cloudinary` | Cloudinaryにアップロード済み |
| `none` | ストレージなし（URLのみ参照） |
| `dry_run` | dry-runで記録のみ（実アップロードなし） |
