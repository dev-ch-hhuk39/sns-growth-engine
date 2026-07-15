# SNS Growth Engine v2 Operator View

Open the Google Sheet first. No source code change is needed for daily review.

| What to check | Sheet tab | Healthy state |
| --- | --- | --- |
| Today's ten slots | `content_slot_runs` | `POSTED_PRIMARY`, `POSTED_FALLBACK`, or `BACKFILLED` with a post URL |
| Latest actual posts | `posted_results` | `status=POSTED`, `metrics_status=PENDING` until measurement arrives |
| Worker health | `autonomous_health` | `apply_status=POSTED` or a specific `no_post_reason` |
| Direct-media authorization | `media_permissions` | explicit non-revoked evidence and all required direct permissions |
| Direct source assets | `source_posts`, `source_post_media`, `media_assets` | linked `source_post_id`, `UPLOADED`, unused asset |
| Clip inventory | `source_videos`, `video_clip_candidates`, `media_assets` | at least three `MEDIA_READY` assets per account |
| Media performance | `media_post_results`, `media_metrics` | URLs and measured values only when actually available |

## Required Actions

1. A `DIRECT_PERMISSION_SOURCE_EMPTY` result means add one row in
   `media_permissions`, with evidence and every requested direct-reuse flag.
   Never change `clip_source` to direct reuse without evidence.
2. A media slot with `POSTED_FALLBACK` is healthy delivery, but means inventory
   needs replenishment. Review the source/asset tabs above.
3. `PENDING`, `UNAVAILABLE`, and `PARTIAL` metrics are not zero. Do not enter
   zero unless the platform has explicitly returned zero.
4. To stop all publishing set `kill_switch=true` in
   `config/autonomous_mode.json`, commit, and push. X and beauty are never
   enabled by this procedure.

## Current External Blocker

GitHub Actions currently reports a billing/spending-limit rejection before job
startup. Restore Actions billing, then run the two text dry-runs, followed by
the documented one-item E2E smokes. Do not call the system complete until URLs
and the linked Sheet rows exist.
