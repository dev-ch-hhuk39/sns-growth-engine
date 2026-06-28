# Cloudinary Setup

Date: 2026-06-28

メディア配信に使う Cloudinary の接続設定と安全ゲートの入口 doc。
実 upload 運用・スモークの詳細は既存 doc を参照する（本 doc は薄い入口）。

## 環境変数

`.env` に以下を設定する（値は表示・コミットしない）:

```
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
```

- 値は `.env` 内のみに保持し、リポジトリへコミットしない。fallback JSON 等にも含めない。

## 実 upload の二重ゲート（重要）

Cloudinary への実 upload は次の二つが両方必要:

1. env フラグ `ALLOW_CLOUDINARY_UPLOAD=true`
2. CLI フラグ `--confirm-upload`

```bash
# 計画のみ（既定・upload しない）
python3 scripts/upload_approved_media.py --account-id night_scout
# 実 upload（本開発中は実行しない）
ALLOW_CLOUDINARY_UPLOAD=true python3 scripts/upload_approved_media.py --account-id night_scout --apply --confirm-upload
```

どちらか一方でも欠けると upload は BLOCKED。既定はドライランで、実 upload はしない。

## 権利・対象の前提

- upload 対象は承認済み（APPROVED）かつ権利クリアな自社生成／許諾済み素材のみ。
- `media_policy=plan_only` の source は Cloudinary upload 不可。`reuse_policy=no_reuse` は media 利用不可。
- 第三者素材を勝手に upload しない。`beauty_account` は対象外。

## 関連 doc

- [cloudinary-upload-runbook.md](cloudinary-upload-runbook.md) — 実 upload 運用手順
- [cloudinary-upload-smoke-test.md](cloudinary-upload-smoke-test.md) — スモークテスト
- [media-asset-storage.md](media-asset-storage.md) — media_assets 保存設計
- [media-reuse-risk-policy.md](media-reuse-risk-policy.md) — 流用リスク・権利ポリシー
