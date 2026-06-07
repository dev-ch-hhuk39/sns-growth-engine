# Cloudinary 小規模アップロードスモークテスト（Phase 2.32）

## 概要

Cloudinaryへの実アップロードを実施する前に、接続確認と安全チェックを行う。

**今回は実アップロードしない。** 実行コマンドはこのドキュメントに記載するが実施しないこと。

## 事前確認

```bash
# 1. 認証情報確認（値は表示しない）
python scripts/test_cloudinary_credentials.py

# 2. dry-run 動作確認
python scripts/test_cloudinary_upload_smoke.py \
  --file tests/fixtures/sample_image.jpg
```

## 安全ガード（3重）

1. `ALLOW_CLOUDINARY_UPLOAD=true` が必要
2. `--upload` フラグが必要
3. `--confirm-upload` フラグが必要

全て揃わない限り実アップロードしない。

## ファイルサイズ制限

- 最大: **512KB**
- 許可拡張子: `.jpg`, `.jpeg`, `.png`, `.webp`, `.mp4`, `.mov`

## 実アップロードコマンド（今回は実行しない）

```bash
ALLOW_CLOUDINARY_UPLOAD=true \
  python scripts/test_cloudinary_upload_smoke.py \
  --file tests/fixtures/sample_image.jpg \
  --upload --confirm-upload
```

## テスト後の削除手順

実アップロード後は必ず削除すること:

1. Cloudinary Media Library にアクセス
2. フォルダ `sns_v2_smoke_test` を開く
3. テストファイルを削除する
4. または API で `DELETE /resources/image/upload/sns_v2_smoke_test/*` を実行

## .env 設定項目

```
CLOUDINARY_CLOUD_NAME=<your_cloud_name>
CLOUDINARY_API_KEY=<your_api_key>
CLOUDINARY_API_SECRET=<your_api_secret>
ALLOW_CLOUDINARY_UPLOAD=false  # テスト時以外は false を維持
```

## 参考

- Cloudinary ダッシュボード: https://cloudinary.com/console
- Media Assets スキーマ: `docs/media-assets-schema.md`
