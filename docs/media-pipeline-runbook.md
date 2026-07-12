# Media Pipeline Runbook

## 2026-07-12 Production Media Path

The production media path is enabled only for source records with both approved permission evidence and `media_autopilot_enabled=true`.

- `liver_manager`: `.github/workflows/media-growth-production.yml`, JST 09:20.
- `night_scout`: `.github/workflows/media-growth-production-night-scout.yml`, JST 12:20.
- Each account has an independent daily media cap of one. Bounded discovery scans at most 12 videos per source, registers at most three new videos per source and twelve in total per run; subsequent runs continue through the remaining back catalogue without duplicate video/clip processing.

1. Daily aftercare saves bounded real video metadata and auto-approved clip candidates that pass rights and public-text checks.
2. The media production workflow selects one unposted clip, downloads the individual source video, creates a 9:16 ffmpeg clip, uploads it to Cloudinary, validates the asset and text, and places a READY media row into the Threads queue.
3. Threads publication waits for the video container to finish and records `source_video_id` and `clip_candidate_id` in `posted_results`.

Every real operation requires the dedicated schedule/dispatch guard and step-scoped environment gates. Unknown or reference-only rights, sources without `media_autopilot_enabled`, X, beauty, missing permission evidence, invalid IDs, duplicate clips, and failed validators are blocked. The daily media cap is one per account, and `kill_switch=true` stops the run.

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

## Owned / Licensed Asset Intake (2026-07-01)

Use `config/source_accounts/owned_media_asset_template.json` for any owned/licensed/approved creator material before it enters `ingest_media_assets.py`.

Human-readable review template: `docs/media-rights-template.md`.

Required permission fields:

- `asset_id`, `platform`, `source_url` or `local_file_ref`
- `owner_name`, `permission_source`, `permission_date`, `expires_at`
- `rights_status`: `owned`, `licensed`, or `approved_creator_clip`
- `allowed_uses`: `cut`, `upload`, `repost`, `derivative_post`
- `target_account_id`, `notes`

TODO placeholders in source registry are not media pipeline eligible. They exist only to show where human URLs/permission evidence are missing.

| rights_status | save | cut | upload | repost | media queue |
|---|---|---|---|---|---|
| `third_party_reference_only` | no | no | no | no | no |
| `unknown` | no | no | no | no | no |
| `owned` | gated | gated | gated | gated | review-only |
| `licensed` | gated | gated | gated | gated | review-only |
| `approved_creator_clip` | gated | gated | gated | gated | review-only |
