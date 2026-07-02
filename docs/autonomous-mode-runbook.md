# Autonomous Mode Runbook

Date: 2026-07-02

## Purpose

Autonomous mode allows the reviewed text-only Threads pilot to run without per-post human approval. It is rules-based automation, not an unrestricted bot.

Initial scope:

- Accounts: `night_scout`, `liver_manager`
- Posting platform: Threads only
- Source fetch platforms: Threads and reviewed YouTube metadata/reference paths only
- Media: disabled
- X: disabled for fetch and post
- `beauty_account`: blocked

## Configuration

Primary config:

```bash
config/autonomous_mode.json
```

Important initial values:

- `autonomous_mode_enabled=true`
- `auto_source_fetch_enabled=true`
- `auto_idea_generation_enabled=true`
- `auto_ready_enabled=true`
- `auto_post_enabled=true`
- `human_review_required=false`
- `daily_post_cap_per_account=1`
- `daily_ready_cap_per_account=2`
- `max_posts_per_run=1`
- `cooldown_minutes=180`
- `max_similarity_to_source=0.55`
- `kill_switch=false`

Existing `config/auto_approval_rules.json` remains integrated for legacy AUTO_READY policy and safety defaults. Autonomous priority order is:

1. kill switch
2. account/platform block
3. rights/media block
4. safety/risk/similarity
5. daily cap/cooldown
6. auto_ready/auto_post gates

## Current Autonomous Sources

The first autonomous pilot uses only reviewed source candidates:

| account_id | source_id | platform | URL | use |
|---|---|---|---|---|
| `night_scout` | `src_ns_threads_required_001` | threads | `https://www.threads.com/@kyaba_ryo` | public reference metadata/text |
| `night_scout` | `src_ns_threads_required_002` | threads | `https://www.threads.com/@mizuno9120` | public reference metadata/text |
| `liver_manager` | `src_lm_yt_cand_001` | youtube | `https://www.youtube.com/@suu-san_pococha` | metadata/transcript analysis only, no download |

TODO placeholders, X sources, beauty sources, unknown-rights media, and media pipeline rows are excluded.

## Commands

Dry-run, no posting:

```bash
python3 scripts/run_autonomous_loop.py --account-id all --dry-run
```

Production apply command:

```bash
python3 scripts/run_autonomous_loop.py --account-id all --apply --confirm-autonomous
```

There is no per-post approval prompt in autonomous mode. The explicit run approval is the command-level `--confirm-autonomous` gate plus the rules in `config/autonomous_mode.json`.

## GitHub Actions

Workflow:

```bash
.github/workflows/autonomous-growth-loop.yml
```

It is `workflow_dispatch` only at initial launch. The apply step runs only when `confirm_autonomous=true`.

The workflow sets:

- `PUBLISH_ENABLED=true`
- `ALLOW_REAL_THREADS_POST=true`
- `ALLOW_REAL_X_POST=false`
- `ALLOW_VIDEO_DOWNLOAD=false`
- `ALLOW_VIDEO_CUT=false`
- `ALLOW_CLOUDINARY_UPLOAD=false`
- `ALLOW_TRANSCRIPTION_API=false`

The apply step also checks `config/autonomous_mode.json` and stops when `kill_switch=true`.

## Hard Blocks

Autonomous mode must not:

- post to X
- fetch X
- post or READY `beauty_account`
- download third-party video
- cut video
- upload to Cloudinary
- use transcription API
- post media
- use unknown-rights or third-party media as reusable media
- exceed one post per account per day or one post per run

## Stopping Bad Posts

Fast stop:

1. Set `kill_switch=true` in `config/autonomous_mode.json`.
2. Commit and push.
3. Disable or avoid running the workflow.
4. If a bad Threads post exists, remove/handle it in Threads manually and mark the related Sheets rows for review.

Pause only posting while keeping planning:

1. Set `auto_post_enabled=false`.
2. Keep `auto_ready_enabled` or `auto_idea_generation_enabled` as needed.
3. Re-run dry-run and confirm `auto_post_plan.enabled=false`.

## Rollback

Rollback the autonomous loop by reverting:

- `config/autonomous_mode.json`
- `.github/workflows/autonomous-growth-loop.yml`
- `scripts/run_autonomous_loop.py`

If apply mode ran and posted, do not re-run the same queue row. `process_threads_queue.py` writes `POSTED_SAVE_FAILED` fallback if Sheets save fails, so use recovery scripts rather than retrying blindly.

## Future Media Conditions

Media can only be considered after all are true:

- source has `rights_status` of `owned`, `licensed`, or `approved_creator_clip`
- permission evidence exists
- `allow_media_posts=true`
- `allow_third_party_media` remains false unless explicit legal review changes policy
- Cloudinary/video download/cut flags are intentionally enabled with separate tests

Until then, all source media is reference analysis only.

## 2026-07-02 Video Reference Connection

`scripts/run_autonomous_loop.py` now includes a video reference analysis step before scoring and queue work.

- Selected YouTube/TikTok pilot sources are analyzed as reference-only inputs.
- YouTube metadata uses the existing safe metadata/transcript path; channel URLs may return transcript `UNAVAILABLE` because no individual `video_id` exists.
- TikTok is connected only for individual `/video/` URLs. TODO placeholders and profile-only URLs are skipped.
- Transcript body/preview is not returned in autonomous output.
- Generated ideas from video references are text-only Threads candidates. They do not attach media.
- Third-party video download, cut, upload, repost, and Cloudinary upload remain blocked.

Initial production apply attempt on 2026-07-02 was not executed because the local approval reviewer rejected the real-post capable command. Do not work around that gate. Re-run only with an explicit operator approval path for real Threads posting.
