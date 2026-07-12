# Growth Loop Runbook

## 2026-07-12 Production Automation Flow

The live production flow is now split to avoid one failing subsystem stopping everything:

1. Account-specific text workflows post safe `public_post_text` to Threads.
2. Aftercare syncs source registry, metrics/PDCA, and discovers approved source videos.
3. Media transcription turns approved individual `source_videos` into `video_transcripts`.
4. Media growth creates only transcript-grounded clip candidates.
5. Media production posts at most one approved video per day.

The July 11 text schedules were firing but failed because Sheets read/write quota was exhausted by row-by-row generation updates and refill setup reads. Those paths now use batched writes and skip production setup initialization.

The July 12 recovery also changed autonomous apply error handling: optional source collection / reference scoring failures are logged as `WARN_NON_BLOCKING` and no longer fail the whole scheduled run when safe fallback generation and final validation can continue. Workflow concurrency is scoped per workflow/account to avoid GitHub Actions pending-run cancellation.

Media posting requires `transcript_grounded=true`; this prevents duration-only or analysis-only candidates from becoming public video posts.

## 2026-07-11 Connected Production Loop

The text-only schedule is unchanged and remains independent of media availability. Reference generation failure is recoverable through a validator-approved original-post fallback.

Approved media now has a separate production schedule. Aftercare discovers a bounded set of real individual video URLs and saves only new `source_videos`; plan-only IDs are excluded. The production runner prefers YouTube candidates, permits distinct non-duplicate clips from the same video, blocks failed candidates from endless retries, and processes at most one media post per day.

The media path is enabled only for `liver_manager` sources listed in `config/media_growth_engine.json` with approved permission evidence. Download, cut, upload, and Threads video publication still require all explicit environment gates inside the scheduled job. X, beauty, reference-only media, unknown-rights media, and automatic learning-rule changes remain blocked.

## Scope

`scripts/run_growth_loop.py` orchestrates the safe v2 planning loop:

1. collect Threads metrics snapshots
2. generate PDCA candidates
3. plan source collection
4. plan media queue generation
5. run AUTO_READY dry-run

For command-level autonomous operation, use `scripts/run_autonomous_loop.py` instead. It reads `config/autonomous_mode.json`, selects only the reviewed pilot sources, keeps X/beauty/media blocked, and can run the initial text-only Threads loop without per-post human approval when `--apply --confirm-autonomous` is used.

## Default Behavior

- Default is dry-run / `PLAN_ONLY`.
- AUTOPOST is always off in this runner.
- Real posting is not executed.
- X posting/fetch is not executed.
- beauty_account is blocked.
- media download/cut/upload is not executed.
- The runner reports `kill_switch_respected=true`; production automation must still check `config/auto_approval_rules.json`.

`run_autonomous_loop.py` is the exception for the approved pilot: `auto_post_enabled=true` in `config/autonomous_mode.json`, but posting is still capped to Threads, max 1 post per run, max 1 per account per day, and requires `--confirm-autonomous` plus the existing Threads worker real-post gates.

## Command

```bash
python3 scripts/run_growth_loop.py --dry-run --account-id all
```

`--apply` is blocked unless `--confirm-run` is also present, and should not be used until metrics, source collection, and AUTO_READY policies are reviewed.

## Real Data Collection Dry-Run (2026-06-30)

`run_growth_loop.py` can now pass real public collection outputs into the existing scoring / idea planning functions without writing Sheets or posting.

```bash
python3 scripts/run_growth_loop.py --dry-run --account-id all \
  --metric-post-url "https://www.threads.com/@ran.liver_pro/post/DaMbCLQiXLs" \
  --metric-post-url "https://www.threads.com/@kyaba_consul_mizu/post/DaNToTqgQ7i" \
  --source-url "https://www.threads.com/@ran.liver_pro/post/DaMbCLQiXLs" \
  --source-url "https://www.threads.com/@kyaba_consul_mizu/post/DaNToTqgQ7i" \
  --fetch-real
```

Expected behavior:

- Threads metrics collection returns `UNAVAILABLE` when public HTML does not expose trusted counts. Unknown values stay `null`; confirmed zero is never invented.
- Threads source collection can produce `source_account_posts`-shaped rows from public OG metadata, with `can_reuse_media=false`.
- `real_collection_pipeline` reports source posts, score count, and `WAITING_REVIEW` candidate count.
- AUTOPOST remains off. No real post, media download, cut, upload, or X action is performed.

Use `--use-sheets` only when intentionally reading existing Sheets state. Do not bulk-enable `fetch_enabled=true`; use `--source-url` or a small reviewed set first.

## Adapter Status Summary

`run_growth_loop.py --dry-run` includes `adapter_status` with metrics/source/video adapter availability:

- metrics: public HTML and optional Playwright browser adapter.
- source: BeautifulSoup/lxml parser, X blocked status, Agent Reach / CLI-Anything optional status.
- video: yt-dlp / youtube-transcript-api availability and download blocked status.

This summary is informational only. It does not enable fetch, upload, or posting. AUTOPOST remains off.

## 2026-07-01 Environment Check

- `pip install -r requirements.txt`: completed.
- Adapter imports: `bs4`, `lxml`, `playwright`, `yt_dlp`, `youtube_transcript_api`, `PIL`, `ffmpeg`, `cloudinary` all import successfully.
- `run_growth_loop.py --dry-run --account-id all`: reports adapter_status and keeps `auto_post=false`, `real_post=false`.
- Public metadata dry-runs may perform HTTP reads for the provided public URLs, but they do not write Sheets, download media, upload media, or post.

## Media Rights Integration (2026-07-01)

Growth loop outputs must keep media out of posting unless the media asset is `owned`, `licensed`, or `approved_creator_clip`.

- Third-party source/video media remains reference-only.
- Media queue generation produces `WAITING_REVIEW` only and excludes reference-only/unknown assets.
- AUTOPOST remains OFF. The loop must not promote media posts to READY.
- Copy-like generated text is blocked by the reference similarity guard before queue planning.

## Source Registry Preconditions (2026-07-01)

- `default_sources.json` currently keeps `fetch_enabled=true` at 0.
- TODO source placeholders are skipped by collection because they have empty `source_url`, `manual_only=true`, and `fetch_enabled=false`.
- Growth loop can use registered references for scoring/idea planning only after humans select a small dry-run source set. Do not bulk-enable source fetch.
- No source registry row is currently `media_pipeline_eligible=true`.
- The local `owned_media_assets_todo` placeholder is also skipped until rights evidence and local/source references are filled.
- Growth loop must not attach reference-only media or promote media candidates to READY. AUTOPOST remains OFF.

## Autonomous Video Reference Pilot (2026-07-02)

`scripts/run_autonomous_loop.py` is the autonomous exception to the normal dry-run growth loop. It now includes:

1. Safe source selection from reviewed pilot candidates.
2. Threads source collection for selected Threads URLs only.
3. YouTube/TikTok reference analysis for selected video references.
4. Text-only Threads idea generation from video structure/hook signals.
5. Scoring, candidate generation, capped AUTO_READY, and capped Threads posting when the real-post command is explicitly approved.

Current invariant gates:

- X fetch/post: blocked.
- `beauty_account`: blocked.
- media post: blocked.
- third-party video download/cut/upload/repost: blocked.
- transcription API: blocked unless separately enabled with the existing confirm/env gates.
- max real posts per autonomous run: 1.

On 2026-07-02 the dry-run passed, but the apply command was stopped by the local approval reviewer because it can perform real Threads posts. No workaround was used.

Production start succeeded through **Autonomous Growth Loop** run `28571552118`, which posted one text-only Threads item. The workflow schedule is now enabled for JST 09:15 daily (`cron: "15 0 * * *"`). Keep `max_posts_per_run=1`, daily caps, X/media/beauty blocks, and use `kill_switch=true` for emergency stop.

## Public Text Gate For Autonomous Posting (2026-07-03)

Autonomous posting now separates internal analysis from public copy. Any generator that returns structured output must keep analysis in `internal_analysis` and put only reader-facing text in `public_post_text`.

The worker and AUTO_READY gate both call `final_public_post_validator`:

- Internal terms, source metadata, queue/result ids, dry-run/apply labels, score fields, URLs, and AI-like analysis notes are blocked.
- Excessive hashtags, aggressive recruitment, easy-money claims, and high-pressure CTA wording are blocked.
- `public_post_quality_score >= 85`, reader value/account fit/naturalness >= 80, CTA pressure <= 30, risk <= 10.
- Blocked READY rows are not posted; in real worker mode they are marked `BLOCKED_INTERNAL_LEAK`.

The autonomous loop dry-run now prints a safe public preview:

- `selected_account`
- `skipped_account`
- `selected_queue_id`
- `public_post_preview`
- `internal_leak_check`
- `account_fit_check`
- `final_validator_result`
- `would_post=false`

Do not include transcript body, source text, or internal analysis in run output.

## Account-Specific Schedule (2026-07-04)

Autonomous scheduled posting now uses account-specific workflows:

- `autonomous-growth-loop-night-scout.yml`
- `autonomous-growth-loop-liver-manager.yml`

The manual `autonomous-growth-loop.yml` remains for `workflow_dispatch` and `account_id=all`; it no longer has a schedule trigger. Account rotation is only relevant for manual `all` runs. Scheduled workflows pass a fixed `ACCOUNT_ID`.

Scheduled target windows:

- `night_scout`: JST 14:00, 16:00, 18:00, 21:00, 25:00.
- `liver_manager`: JST 10:00, 13:00, 16:00, 18:00, 21:00.

Each scheduled workflow starts 15 minutes before the target time and sleeps a random 0-1800 seconds before dry-run/apply. Only the sleep seconds are printed. Secrets are not printed.

Caps:

- `daily_post_cap_per_account=5`
- `daily_ready_cap_per_account=8`
- `max_posts_per_run=1`
- `cooldown_minutes=90`

All existing blocks remain for scheduled text-only autonomous posting: X fetch/post false, beauty blocked, media post false, third-party/unknown-rights download/cut/upload/repost false, Cloudinary upload false, transcription API false.

## Media Growth Engine (2026-07-04)

`liver_manager` now has a dry-run Media Growth Engine for user-approved YouTube/TikTok references:

- Sources with `rights_status=approved_creator_clip`, `permission_status=approved`, and permission evidence can be selected for media planning.
- Channel/account URLs can seed metadata/transcript plans and clip candidate ideas, but are not direct download targets. Real download requires an individual video URL.
- `run_media_growth_engine.py --account-id liver_manager --dry-run` produces rights checks, transcript/metadata status, clip candidates, a `public_post_preview`, and a PDCA plan without saving media or posting.
- Real download/cut/upload/video post remains manual-only and gated by env vars plus `--confirm-*` flags.
- Scheduled text-only workflows are unchanged and do not post media.
- PDCA records from media are suggestions only; learning rules remain `active=false` / `auto_apply=false`.

### Source Video Discovery

`scripts/discover_approved_source_videos.py --account-id liver_manager --dry-run` builds a bounded discovery plan from approved source channels/accounts. It shows selected sources, source-level limits, duplicate counts, and a preview of new `source_videos` candidates. Dry-run does not write to Sheets or local archive.

Current defaults:

- `source_video_discovery_enabled=true`
- `source_video_discovery_apply_enabled=false`
- `max_videos_per_source_scan=50`
- `max_new_videos_per_source_per_run=10`
- `max_total_new_videos_per_run=20`
- `allow_multiple_clips_per_video=true`
- `max_clip_candidates_per_video=3`
- `clip_overlap_policy=block_overlapping_ranges`

`run_media_growth_engine.py` now prefers `source_videos`; if none are saved yet, it uses the dry-run discovery plan as the candidate source. Download/cut/upload/video post remain false.

## Autonomous Text-Only Recovery (2026-07-07)

`run_autonomous_loop.py` is the production text-only automation entrypoint. Scheduled Actions were running, but posting stopped because read-only Sheets verification failed on registry reflection checks and the runner treated that as a hard apply blocker.

Current recovery behavior:

1. `run_autonomous_loop.py --apply --confirm-autonomous --account-id <account>` performs a credential/safety preflight.
2. `recover_production_sheets_threads_first.py --verify-only --json` failure is recorded as a warning, not a hard stop.
3. Threads source fetch, video reference analysis, and reference scoring are allowed to soft-fail.
4. If reference rows are empty, `generate_threads_ideas_from_references.py` creates safe original fallback `WAITING_REVIEW` candidates.
5. If reference-generated rows already exist but are stale/rejected, generation refreshes non-locked rows with current validated public text.
6. If every reference-generated row is locked/skipped, generation adds timestamped safe fallback candidates so AUTO_READY has fresh inventory.
5. `auto_approve_queue.py` promotes only passing text-only candidates to `READY`.
6. `process_threads_queue.py` posts only `READY` and writes `posted_results` / PDCA initial records.
7. If no post happens, `health_summary.no_post_reason` identifies the cause.

Read-only health:

```bash
python3 scripts/check_autonomous_health.py --account-id all --dry-run
```

Production schedules:

- `night_scout`: JST 14:00, 16:00, 18:00, 21:00, 25:00 with 0-1800s jitter.
- `liver_manager`: JST 10:00, 13:00, 16:00, 18:00, 21:00 with 0-1800s jitter.

Caps remain:

- `daily_post_cap_per_account=5`
- `daily_ready_cap_per_account=8`
- `max_posts_per_run=1`
- `cooldown_minutes=90`

Media Growth Engine remains separate: media schedule OFF; download/cut/upload/video post require explicit env+confirm gates and are not part of text-only scheduled posting.

## READY / AUTO_READY Diagnostics (2026-07-09)

The loop now records enough information to distinguish "workflow success" from "post success".

Important fields in `health_summary` and the `autonomous_health` tab:

- `ready_count`: how many rows AUTO_READY promoted in this run.
- `checked_count`: how many queue candidates AUTO_READY evaluated.
- `approved_count`: how many candidates passed AUTO_READY.
- `rejected_count`: how many candidates failed AUTO_READY.
- `processed_count`: how many READY rows the worker attempted.
- `posted_count`: how many Threads posts succeeded.
- `no_post_reason`: the reason if `posted_count=0`.

Useful no-post reasons:

- `NO_READY_QUEUE`
- `AUTO_READY_REJECTED_ALL`
- `VALIDATOR_BLOCKED_ALL`
- `DUPLICATE_BLOCKED_ALL`
- `DAILY_CAP_REACHED`
- `COOLDOWN_ACTIVE`
- `THREADS_API_FAILED`
- `POSTED_SAVE_FAILED`

Queue diagnostics now live directly on `queue` rows:

- `public_post_text`
- `validator_status`
- `internal_leak_status`
- `account_fit_status`
- `quality_score`
- `safety_score`
- `risk_score`
- `rejected_reason`
- `blocked_reason`

Before allowing a real post, operators can verify READY creation without posting:

```bash
python3 scripts/run_autonomous_loop.py --account-id night_scout --apply --confirm-autonomous --stop-before-post
python3 scripts/run_autonomous_loop.py --account-id liver_manager --apply --confirm-autonomous --stop-before-post
```

This writes only the planning/generation/AUTO_READY side and skips `process_threads_queue.py`. Do not use it as a substitute for the scheduled workflow; it is a production diagnostic.

## Production Autopilot Aftercare (2026-07-10)

The production growth loop now has three scheduled layers:

- `Autonomous Growth Loop Night Scout`: text-only Threads publishing for `night_scout`.
- `Autonomous Growth Loop Liver Manager`: text-only Threads publishing for `liver_manager`.
- `Production Autopilot Aftercare`: non-posting aftercare for metrics, PDCA candidates, approved source video discovery, and clip candidates.

The aftercare workflow runs daily at JST 23:40. It may write safe operational records to Sheets when `confirm_aftercare=true` or the event is `schedule`, but it keeps all public-post and media execution gates closed:

- `PUBLISH_ENABLED=false`
- `ALLOW_REAL_THREADS_POST=false`
- `ALLOW_REAL_X_POST=false`
- `ALLOW_MEDIA_POSTS=false`
- `ALLOW_VIDEO_DOWNLOAD=false`
- `ALLOW_VIDEO_CUT=false`
- `ALLOW_CLOUDINARY_UPLOAD=false`
- `ALLOW_TRANSCRIPTION_API=false`

The media side that is now automated is discovery/planning only:

- approved `liver_manager` sources are discovered into `source_videos`
- dedupe uses `platform`, `source_id`, `video_id`, and canonical URL
- clip candidates are generated into `video_clip_candidates`
- public post previews must pass the final public validator

The media side that remains manual/gated:

- real download
- real ffmpeg cut
- Cloudinary upload
- Threads video+text post
- learning_rules auto-apply

Local dry-run checks:

```bash
python3 scripts/check_autonomous_health.py --account-id all --dry-run
python3 scripts/discover_approved_source_videos.py --account-id liver_manager --dry-run
python3 scripts/run_media_growth_engine.py --account-id liver_manager --dry-run
```
