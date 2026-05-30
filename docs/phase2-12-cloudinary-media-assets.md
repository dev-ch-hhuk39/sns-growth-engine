# Phase 2.12: Cloudinary media_assets 統合

**実施日**: 2026-05-30

---

## 概要

`reference_posts` に保存された画像URL・動画URLをもとに、`media_assets` タブへ保存・管理する基盤を構築する。

Cloudinaryへの実アップロードは `ALLOW_CLOUDINARY_UPLOAD=true` が設定されている場合のみ行う（デフォルト: false）。

分析エンジン: `src/media/cloudinary_client.py`
CLI: `scripts/prepare_media_assets.py`

---

## 実装ファイル

| ファイル | 役割 |
|---|---|
| `src/media/cloudinary_client.py` | メディアURL抽出・ダウンロード・Cloudinaryアップロード・リスク判定 |
| `src/config_loader.py` | `get_cloudinary_config()` 追加 |
| `scripts/prepare_media_assets.py` | メディア準備 CLI |
| `scripts/test_phase212.py` | Phase 2.12 テスト |
| `fixtures/sample_media_assets.json` | テスト用ダミーデータ |

---

## 実装した関数（cloudinary_client.py）

| 関数 | 説明 |
|---|---|
| `extract_media_urls(post)` | `media_urls`（パイプ区切り）から URL リストを返す |
| `classify_media_url(url)` | URL から `image` / `video` / `unknown` を判定 |
| `safe_slug(text, fallback)` | ファイル名安全な slug に変換 |
| `build_public_id(reference_post_id, account_id, index)` | Cloudinary public_id を生成 |
| `cloudinary_signature(params, api_secret)` | Cloudinary API 署名（SHA-1） |
| `download_media(url)` | URL からメディアをダウンロード → (bytes, mime_type) |
| `upload_to_cloudinary(data, mime_type, public_id, config)` | Cloudinary へ POST アップロード |
| `assess_imitation_risk(post)` | メディアの模倣リスクを判定 → `low` / `medium` / `high` |
| `prepare_media_asset(post, account_id, config, dry_run)` | 1件分のメディアアセット準備 |
| `prepare_media_assets(posts, account_id, config, dry_run)` | バッチ処理 |

---

## Cloudinary アップロード安全ガード（2重）

```
dry_run=True     → アップロードしない（デフォルト）
ALLOW_CLOUDINARY_UPLOAD != true → アップロードしない（デフォルト false）
```

両方が解除された場合のみ実際の HTTP POST を送信する。

---

## public_id 命名規則

```
sns-growth-engine/{account_id}/{reference_post_id}-{index:02d}
```

例: `sns-growth-engine/night_scout/post_abc123-00`

---

## media_assets のユニークキー

`reference_post_id + original_media_url` の組み合わせでアップサート。
1件の投稿に複数メディアURLが含まれる場合、それぞれ別行として保存する。

---

## storage_url の値

| 状態 | storage_url |
|---|---|
| dry-run（アップロードなし） | `""` （空文字） |
| 実アップロード成功 | Cloudinary の `secure_url` |

---

## reference_post_id + original_media_url でのアップサート

`SheetsClient.save_media_asset()` は `reference_post_id + original_media_url` を複合キーとしてアップサートを行う。

---

## SheetsClient に追加したメソッド

| メソッド | 説明 |
|---|---|
| `get_media_assets(account_id, reference_post_id, limit)` | media_assets タブから取得 |
| `find_media_asset_by_reference_post_id(reference_post_id)` | 1件引き当て（最初の1件） |
| `find_media_asset_by_original_media_url(original_media_url)` | URL で引き当て |
| `save_media_asset(asset)` | reference_post_id + original_media_url でアップサート |
| `save_media_assets(assets)` | バッチ保存 |

MockSheetsClient にも同じメソッドを追加済み。

---

## prepare_media_assets.py の使い方

```bash
# JSONフィクスチャ → dry-run（Sheetsへ書かない / Cloudinaryへ送らない）
python scripts/prepare_media_assets.py \
  --account-id night_scout \
  --input-json fixtures/sample_x_posts.json \
  --dry-run

# Sheetsから reference_posts を読んで準備（dry-run）
python scripts/prepare_media_assets.py \
  --account-id night_scout \
  --use-sheets \
  --dry-run

# Sheetsへ書き込み（Cloudinaryアップロードなし）
python scripts/prepare_media_assets.py \
  --account-id night_scout \
  --use-sheets \
  --test-write \
  --no-dry-run
```

### 安全フラグ

| フラグ | 説明 |
|---|---|
| `--dry-run` | Sheetsへの書き込みをスキップ（デフォルト ON） |
| `--no-dry-run` | Sheetsへの書き込みを有効化 |
| `--use-sheets` | 実SheetsClient を使用 |
| `--test-write` | 実Sheetsへ書き込みを実行（--use-sheetsと組み合わせる） |
| `--upload` | `ALLOW_CLOUDINARY_UPLOAD=true` のときのみ有効（実アップロード） |

---

## 次のフェーズ

- Phase 2.13: `generation_planner.py` で 8:2 生成計画を generation_jobs に書き込む
