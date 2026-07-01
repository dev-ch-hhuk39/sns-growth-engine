# Media Pipeline Runbook

## Scope

The v2 media pipeline is review-first. It can plan media queue rows and gated asset operations, but it does not post media by default.

## Safety Gates

- Third-party media is `third_party_reference_only` and cannot be downloaded, cut, uploaded, or reposted.
- Cut is allowed only for `owned`, `licensed`, or `approved_creator_clip`.
- `cut_approved_clips.py --cut` requires `--confirm-cut` and `ALLOW_VIDEO_CUT=true`.
- `upload_media_assets.py --upload` requires `--confirm-upload` and `ALLOW_CLOUDINARY_UPLOAD=true`.
- Media queue generation creates `WAITING_REVIEW` only. It never writes `READY`.
- AUTO_READY initially excludes media posts.

## Commands

```bash
python3 scripts/generate_media_post_queue.py --dry-run
python3 scripts/cut_approved_clips.py --dry-run --rights-status third_party_reference_only
python3 scripts/upload_media_assets.py --account-id night_scout --dry-run
```

Production cut/upload requires explicit rights review before the confirm flags are used.

# Dependency Adapter Notes (2026-06-30)

- `ffmpeg-python`: requirementsに追加。`cut_approved_clips.py` のadapter statusで検出する。ただし実cutにはsystem `ffmpeg` CLIも必要。
- `ffmpeg` CLI: `owned` / `licensed` / `approved_creator_clip` のみcut可能。`ALLOW_VIDEO_CUT=true` + `--confirm-cut` 必須。
- `cloudinary`: requirementsに追加。`upload_media_assets.py` のadapter statusで検出する。
- Cloudinary実upload: `ALLOW_CLOUDINARY_UPLOAD=true` + `--confirm-upload` 必須。third-party/reference-only mediaはBLOCKED。
- `pillow`: requirementsに追加。今後の画像検証用。現時点では実upload/postには使わない。

Third-party videos/images remain reference-only unless rights are explicitly owned/licensed/approved. Do not download, cut, upload, or repost third-party media from this pipeline.

## 2026-07-01 Verification

- `ffmpeg-python` imports as `ffmpeg`.
- `cloudinary` imports successfully.
- `cut_approved_clips.py --dry-run --rights-status third_party_reference_only` remains `BLOCKED`.
- `upload_media_assets.py --account-id night_scout --dry-run` remains `BLOCKED` for third-party/reference-only media.
- No real cut or upload was executed.

## Rights-Aware Media Ingestion (2026-07-01)

Unified rights statuses:

- `third_party_reference_only`: metadata/transcript/analysis only. No save, download, cut, upload, queue media use, or repost.
- `unknown`: blocked until human rights approval. Do not treat unknown as zero-risk.
- `owned`, `licensed`, `approved_creator_clip`: eligible for media asset planning and later gated cut/upload.

Use the new ingestion planner for approved material only:

```bash
python3 scripts/ingest_media_assets.py --account-id night_scout \
  --platform local --source-url "https://example.com/owned.mp4" \
  --rights-status owned --dry-run
```

The CLI creates a `media_assets`-shaped plan row only. URL inputs are not downloaded. Cloudinary upload remains a separate gate and was not executed in this turn.
