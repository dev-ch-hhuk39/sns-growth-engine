# Video Clip Execution

## Purpose

Phase 13 adds a video clip execution planner that keeps ffmpeg work behind explicit confirmation gates. It does not create clip files during dry-run or when source rights are unresolved.

## Files

- `src/video/video_clip_executor.py`: builds `clip_execution_runs` and optional generated clip `media_assets`.
- `scripts/cut_video_clips.py`: existing ffmpeg CLI, now accepts `--mock` and returns `BLOCKED` when `--cut` is used without `--confirm-cut`.
- `scripts/test_phase13_video_clip_execution.py`: confirms no clip file/media asset is produced without confirmation.

## Required Gates

- `--cut --confirm-cut` are both required.
- Source `candidate_status` must be `approved`.
- `rights_policy=unknown` blocks clip use and requires review.
- `media_policy=plan_only` and `do_not_download` block generated clip usage.
- `analysis_only` source media cannot be cut/uploaded/posted.

## Output Records

`clip_execution_runs` include:

- `clip_execution_id`
- `source_id`
- `clip_candidate_id`
- `status`
- `dry_run`
- `cut`
- `confirm_cut`
- `local_path`
- `media_asset`
- `blocked_reasons`
- `warnings`
- `created_at`

## Verification

- `python3 scripts/test_phase13_video_clip_execution.py`
- `python3 scripts/cut_video_clips.py --account-id liver_manager --mock --dry-run`
- `python3 scripts/cut_video_clips.py --account-id liver_manager --cut --dry-run`
