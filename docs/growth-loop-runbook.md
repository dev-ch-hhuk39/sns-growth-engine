# Growth Loop Runbook

## Scope

`scripts/run_growth_loop.py` orchestrates the safe v2 planning loop:

1. collect Threads metrics snapshots
2. generate PDCA candidates
3. plan source collection
4. plan media queue generation
5. run AUTO_READY dry-run

## Default Behavior

- Default is dry-run / `PLAN_ONLY`.
- AUTOPOST is always off in this runner.
- Real posting is not executed.
- X posting/fetch is not executed.
- beauty_account is blocked.
- media download/cut/upload is not executed.
- The runner reports `kill_switch_respected=true`; production automation must still check `config/auto_approval_rules.json`.

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
