# Intent Gap Audit - 2026-07-13

## Conclusion

The intended product is clear: two Threads operating accounts use separate reference pools, while only explicitly permitted creator sources can feed a media pipeline that discovers videos, analyses them, creates clips, stores assets, publishes video + text, and learns from results.

The implementation has the major runners and safety gates, but it is not yet the requested slot-based content operating system. The largest gaps are scheduling/mix orchestration, real reference-grounded writing, saved-media reuse, operational proof from Sheets/Actions, and measured-metrics PDCA.

## What The Current Code Actually Does

| Area | Current state | Assessment |
| --- | --- | --- |
| Text-only Threads | `night_scout` and `liver_manager` each have five scheduled slots with 0-1800s jitter, generated public-only text, AUTO_READY, queue, publisher, and posted-results paths. | Implemented, but live Sheets/post verification is unavailable from this local audit. |
| Posting safety | `public_post_text` is separated from internal analysis; final validator blocks internal terms. X and beauty posting are blocked. | Implemented. |
| Reference sources | Registry records Threads/X/YouTube/TikTok sources and distinguishes many of them with rights and manual/fetch flags. | Partial: role is represented by many flags rather than one canonical role. |
| Reference collection | `night_scout` currently has one directly fetch-enabled Threads source. Other registered Threads sources are still manual-only/fetch-disabled. | Partial. The autonomous plan can select a pilot source, but selection does not itself change its registry fetch flag. |
| Text generation from references | Scoring and generation runners exist, with a safe original fallback pool. | Partial: the autonomous video-reference call is dry-run/non-blocking, so scheduled text posts can fall back to templates rather than being demonstrably grounded in newly collected reference data. |
| Approved media sources | 4 liver_manager sources and 9 night_scout YouTube sources have explicit `approved_creator_clip`, permission evidence, and `media_autopilot_enabled=true`. | Implemented. Unregistered/TODO URLs remain excluded. |
| Media execution | Bounded discovery -> source_videos -> transcript -> clip candidate -> download -> 9:16 cut -> Cloudinary -> Threads video queue -> posted_results is implemented. Separate media workflows are scheduled for liver_manager and night_scout. | Implemented as a runner chain; the latest external end-to-end record still needs verification from Actions/Sheets. |
| Clip-caption relationship | Transcript selects clip ranges and a final validator checks the caption. | Partial: current public captions are account templates by index, not a structured rewrite grounded in the selected transcript excerpt/title/hook. |
| Captions burned into video | Media config says subtitles are enabled. | Missing in production runner: it currently calls the cutter with `burn_subtitles=False`. |
| Saved-media reuse | Media assets and media queue fields exist. | Missing as an operating route: production selects a new unposted clip, not a planned `saved_media_post` / reuse queue type. |
| Metrics and PDCA | Snapshots, PENDING/PARTIAL/MEASURED states, PDCA candidates, and non-auto-applied learning rules exist. | Partial: real metrics collection/Sheets evidence has not been verified in this audit; learning rules remain intentionally non-automatic. |
| Health monitoring | Health CLI covers text workflows, liver media workflow, config and schema expectations. | Partial: it does not yet model the Night Scout media workflow as a first-class workflow check. |

## Manual Differences

The supplied manual is directionally correct but contains an older media status.

- Statements that `download_enabled`, `cut_enabled`, `upload_enabled`, `video_post_enabled`, Cloudinary, and media schedules are OFF are no longer current. Those flags and the dedicated liver/night media workflows are ON for the explicitly permitted sources.
- Statements that every normal posting slot is text-only are still true. Media has been added as an extra daily workflow, not as a declared post type inside one of the five account slots.
- The manual treats all registered Night Scout YouTube sources as reference-only. The current registry now treats the nine user-authorized Night Scout YouTube sources as approved media sources. This follows the later user permission confirmation and should be the new source-of-truth.

## Important Design Conflict To Fix First

Today each account has five text slots and a daily post cap of five. The media workflow is an additional posting attempt.

- liver_manager media runs at JST 09:20, while the first text window is JST 09:45-10:15. With a 90-minute cooldown, the first text run will be suppressed after a media post.
- night_scout media runs at JST 12:20, while the first text window begins JST 13:45. The first five minutes of that text window can still collide with the 90-minute cooldown.
- A successful media post also consumes the shared cap of five, so the current model means at most five total posts, not five text posts plus one media post.

This is intentional safety behavior in the current code, but it does not express the user's desired content mix. A post-slot model is required.

## Required Completion Work

1. Add a canonical `content_schedule` / post-slot configuration. Each slot must declare account, target time, jitter, post type, source pool, fallback type, cooldown rule, and cap contribution. Example post types: `text_only_fallback`, `reference_based_text`, `approved_clip_candidate`, `saved_media_post`, and `pdca_repost_variant`.
2. Make the three source roles explicit in the registry: `posting_account`, `reference_only`, and `approved_media`. Keep `reference_autopilot_enabled` separate from `media_autopilot_enabled`; do not overload `fetch_enabled` or `manual_only`.
3. Connect bounded reference collection to the text generation job in apply mode. Persist normalised reference posts/scores, then create transformed post angles with a similarity guard. Fallback templates should be a true fallback, not the normal source of content.
4. Create transcript-grounded caption generation. The caption must be a new transformation of selected hook/excerpt/title/angle, cite neither source nor transcript, and retain the final public validator.
5. Add a real asset state machine and queue mix: `NEW_CLIP`, `UPLOADED_UNUSED`, `POSTED`, `REUSE_ELIGIBLE`, `EXHAUSTED`. This enables saved-media posts without re-cutting or re-uploading the same asset and prevents duplicate text/clip combinations.
6. Make subtitle behavior real: either burn approved subtitles into clips when `subtitle_enabled=true` or set the config false until it is implemented. The current mismatch must not remain silent.
7. Add account-specific media health checks, Actions summaries, Sheets counts, and an operational dashboard/report that distinguishes `NO_CANDIDATE`, `COOLDOWN`, `DAILY_CAP`, `CREDENTIALS`, `SHEETS`, `PUBLISH_FAILED`, and `POSTED`.
8. Verify real metrics ingestion for posted URLs. Preserve unknown as null; create PDCA suggestions from measured data only; keep learning-rule auto-apply disabled.
9. Enforce Night Scout visual subject policy in the media pipeline. The registry declares female-subject/no-male-scout/no-store-PR constraints, but the current production selector does not perform a visual/content eligibility check for them.

## Evidence Limits In This Audit

- Local dry-runs pass and show public-text validation, source selection, and media plans.
- GitHub Actions and Sheets live data could not be read during this audit because the local GitHub API request could not connect and local credentials are intentionally absent. This is not proof that the external records are correct or incorrect.
- No real fetch, media download, cut, upload, or post was triggered by this audit.

## Remediation Implemented In This Turn

The following audit gaps are now implemented locally and covered by focused
regression checks:

1. A canonical `content_schedule.json` assigns one media slot inside each
   account's five-slot cap. Text schedules no longer compete with media posts.
2. `source_role` and `reference_autopilot_enabled` are normalized separately
   from media authorization. X and beauty remain excluded.
3. The autonomous text runner fetches only actually enabled reference sources;
   it no longer reports an always-dry-run video collection as live input.
4. Reference and transcript signals now choose a transformed reader-facing
   topic. Raw source/transcript text remains private and `public_post_text`
   alone is publishable.
5. Media operation is split into advance `MEDIA_READY` preparation and a
   saved-approved-media posting workflow. The post window never downloads,
   cuts, uploads, or transcribes.
6. Subtitle burn-in is explicitly disabled by user policy.
7. Health checks include both preparation and media-post workflows.
8. Night Scout enforces an explainable female-subject evidence gate; uncertain
   videos are analysis-only rather than silently becoming clips.

Remaining evidence limit: this local environment does not have reusable live
Sheets/GitHub API connectivity, so the first scheduled Actions runs must still
be checked in `autonomous_health`, `source_videos`, `video_clip_candidates`,
`media_assets`, and `posted_results`.
