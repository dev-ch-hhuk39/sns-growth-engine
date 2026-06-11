# Cloudinary Upload Runbook

## 1. 認証情報の設定項目

`.env` に以下を設定する:

```env
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
ALLOW_CLOUDINARY_UPLOAD=false   # 実行直前のみ true に変更
```

設定確認:
```bash
python scripts/test_cloudinary_credentials.py
```

## 2. 画像/動画の小規模テスト条件

smoke test用ファイルの要件:

| 種別 | 最大サイズ | 形式 | 推奨サイズ |
|------|-----------|------|-----------|
| 画像 | 10MB | jpg/png/gif/webp | 100KB以下 |
| 動画 | 100MB | mp4/webm | 1MB以下 |

テスト用ファイルの用意:
```bash
# 小さい画像（既存のfixture画像を使用）
ls tests/fixtures/*.jpg tests/fixtures/*.png 2>/dev/null

# テスト用ダミー画像を作成する場合
python -c "
import base64, pathlib
# 1x1 pixel PNG（最小サイズ）
data = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
pathlib.Path('tests/fixtures/smoke_test_1px.png').write_bytes(data)
print('テスト用画像を作成しました')
"
```

## 3. 実行コマンド

```bash
# Step 1: 認証情報確認（実アップロードなし・常時安全）
python scripts/test_cloudinary_credentials.py

# Step 2: smoke upload（実アップロードには以下が全て必要）
# - ALLOW_CLOUDINARY_UPLOAD=true に変更後
# - --upload --confirm-upload を指定
# - 小さいファイル（上記条件内）
python scripts/test_cloudinary_upload_smoke.py \
  --file tests/fixtures/smoke_test_1px.png \
  --upload \
  --confirm-upload

# Step 3: アップロード後すぐにファイルを削除 → Step 4参照
# Step 4: ALLOW_CLOUDINARY_UPLOAD=false に戻す → Step 5参照
```

## 4. アップロード後の削除手順

テスト後は Cloudinary からファイルを削除する:

```bash
# public_id を確認してから削除
python -c "
import cloudinary, cloudinary.uploader, os
cloudinary.config(
  cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
  api_key=os.environ.get('CLOUDINARY_API_KEY'),
  api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
)
# smoke testで作成したファイルを削除
result = cloudinary.uploader.destroy('sns_growth_engine/smoke_test/smoke_test_1px')
print('削除結果:', result)
"
```

または Cloudinary Dashboard から手動削除。

## 5. ALLOW_CLOUDINARY_UPLOAD=false へ戻す手順

実アップロード後は**必ず**以下を実施する:

```bash
# .env を開いて ALLOW_CLOUDINARY_UPLOAD=false に戻す
# または:
python -c "
import re, pathlib
env = pathlib.Path('.env').read_text()
env = re.sub(r'ALLOW_CLOUDINARY_UPLOAD=true', 'ALLOW_CLOUDINARY_UPLOAD=false', env)
pathlib.Path('.env').write_text(env)
print('ALLOW_CLOUDINARY_UPLOAD=false に戻しました')
"

# 確認
python scripts/test_cloudinary_credentials.py
```

## 6. Cloudinary public_id 命名方針

| 種別 | public_id フォーマット |
|------|----------------------|
| 本番メディア | `sns_growth_engine/{account_id}/{media_type}/{uuid}` |
| smoke test | `sns_growth_engine/smoke_test/{filename}` |
| テストデータ | `sns_growth_engine/test/{date}/{filename}` |

smoke test ファイルは実行後に必ず削除する。

## 7. media_assets タブとの接続方針

アップロード成功後は `media_assets` タブに記録する:

```json
{
  "media_asset_id": "ma_{uuid}",
  "account_id": "night_scout",
  "cloudinary_public_id": "sns_growth_engine/night_scout/image/{uuid}",
  "cloudinary_url": "https://res.cloudinary.com/...",
  "media_type": "image",
  "upload_status": "uploaded",
  "uploaded_at": "2025-06-09T00:00:00Z"
}
```

smoke test データは `is_test_data=true` で記録し、本番投稿には使用しない。

## 関連ファイル

- `scripts/test_cloudinary_credentials.py` - 認証情報確認
- `scripts/test_cloudinary_upload_smoke.py` - smoke upload実行
- `docs/cloudinary-upload-smoke-test.md` - smoke test手順詳細
- `docs/media-assets-schema.md` - media_assets スキーマ定義
