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
