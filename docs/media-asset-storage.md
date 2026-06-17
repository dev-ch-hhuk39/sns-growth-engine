# Media Asset Storage

## Purpose

Phase 13 adds a safe media asset planning layer. It registers candidate image/video assets from `raw_source_items.image_urls` and `raw_source_items.video_urls` into `media_assets` style records without downloading, cutting, uploading, or posting.

## Files

- `src/media/media_asset_store.py`: builds `media_assets`, media queue candidates, and policy preflight results.
- `src/media/media_downloader.py`: plans downloads and blocks missing `--download --confirm-download`.
- `src/media/image_asset_pipeline.py`: image-only helper wrapper.
- `src/media/video_asset_pipeline.py`: video-only helper wrapper.
- `src/media/cloudinary_uploader.py`: Cloudinary upload planner.
- `scripts/preflight_media_assets.py`: dry-run media preflight CLI.
- `scripts/download_media_assets.py`: dry-run/download gate CLI.
- `scripts/upload_media_assets.py`: dry-run/upload gate CLI.

## Safety Rules

- `candidate_status=approved` is required for download/cut/upload.
- `rights_policy=unknown` becomes `WAITING_REVIEW` and blocks media use.
- `reuse_policy=no_reuse` blocks media use.
- `media_policy=do_not_download` blocks download.
- `media_policy=plan_only` blocks save/post use.
- `analysis_only` sources are blocked for media use.
- Cloudinary upload requires `ALLOW_CLOUDINARY_UPLOAD=true` and `--upload --confirm-upload`.
- `beauty_account` media remains review-only.

## Storage Fields

`media_assets` records include:

- `media_asset_id`
- `account_id`
- `source_id`
- `raw_item_id`
- `media_type`
- `external_url`
- `local_path`
- `cloudinary_url`
- `status`
- `rights_policy`
- `reuse_policy`
- `media_policy`
- `clip_execution_id`
- `created_at`

## Verification

- `python3 scripts/test_phase13_media_asset_storage.py`
- `python3 scripts/test_phase13_media_post_preflight.py`
- `python3 scripts/preflight_media_assets.py --account-id night_scout --mock --dry-run`
- `python3 scripts/download_media_assets.py --account-id night_scout --download --dry-run`
- `python3 scripts/upload_media_assets.py --account-id night_scout --upload --dry-run`
