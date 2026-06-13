# media_ingestion_pipeline

動画URL / 画像URL / ローカルファイル → media_assets への安全な登録（Phase 7.C）。

## 概要

- 実ダウンロードはデフォルト禁止（`--download --confirm-download` が必要）
- Cloudinary upload は `ALLOW_CLOUDINARY_UPLOAD=true` かつ `--upload --confirm-upload` が必要
- rights_status=unknown → `reuse_risk=high` → upload BLOCKED
- dry-run でプランのみ作成

## フロー

```
input (url / local_file)
  → create_ingestion_plan()
  → build_media_asset()  ← 実アップロードなし
  → upload_status判定（BLOCKED系 / LOCAL_READY / DOWNLOADED_NOT_UPLOADED）
  → media_assets 登録候補
```

## upload_status 一覧

| status | 意味 |
|--------|------|
| BLOCKED_NO_DOWNLOAD_PERMISSION | --download --confirm-download なし |
| BLOCKED_CLOUDINARY_UPLOAD_DISABLED | ALLOW_CLOUDINARY_UPLOAD=false |
| BLOCKED_NO_UPLOAD_CONFIRMATION | --upload --confirm-upload なし |
| BLOCKED_HIGH_REUSE_RISK | media_reuse_risk=high（rights=unknown） |
| LOCAL_FILE_NOT_FOUND | ファイルが存在しない |
| LOCAL_READY | ローカルファイル準備完了 |

## 使い方

```bash
# dry-run（プランのみ）
python scripts/ingest_media_asset.py --account-id night_scout \
  --video-url "https://example.com/sample.mp4" --dry-run

# ローカルファイル
python scripts/ingest_media_asset.py --account-id night_scout \
  --local-file /path/to/video.mp4 --rights-status owned --dry-run
```

## 安全ルール

- Cloudinary upload は絶対に明示許可なしで実行しない
- `ALLOW_CLOUDINARY_UPLOAD=true` は本番運用時のみ
- media_reuse_risk=high の media は投稿不可
- rights_status=unknown は WAITING_REVIEW
