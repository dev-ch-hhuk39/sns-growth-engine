# Growth Loop Runbook

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

All existing blocks remain: X fetch/post false, beauty blocked, media post false, third-party download/cut/upload/repost false, Cloudinary upload false, transcription API false.
