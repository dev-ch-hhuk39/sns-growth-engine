# Source Backend Decision

## Reference discovery

One bounded PRIMARY backend runs for a capability. A configured FALLBACK runs
only after a real failure. Reference ordering is TikTok -> Threads -> X ->
YouTube.

| Capability | PRIMARY | FALLBACK | Role |
| --- | --- | --- | --- |
| TikTok profile posts | `yt-dlp` | bounded `gallery-dl` metadata | reference only |
| Threads public posts | own public HTTP adapter | none | reference only |
| X registered profile posts | bounded `gallery-dl` metadata | manual/browser export outside active router | reference discovery |
| YouTube channel videos | `yt-dlp` | none | reference + approved physical media |
| YouTube transcript | `youtube-transcript-api` | yt-dlp subtitles, local faster-whisper | understanding |

No Playwright/browser/session backend is active for Threads or TikTok desired
routes. Legacy adapters remain in the factory for rollback and historical
tests, but `config/source_backend_routing.json` cannot select them. Active
acquisition workflows do not install Chromium or provide storage state.

## Physical media

The stable allowlist is X + YouTube only, both through `yt-dlp` on an exact
individual post/video URL after the live permission ledger passes. TikTok and
Threads remain valid reference sources but new physical acquisition is
deferred.

X profile discovery is metadata-only, ignores user gallery-dl configuration,
disables Retweets/quotes/replies/conversations/expand, requests at most 20
items and accepts only `/status/<id>` URLs whose handle equals the registered
source handle. It never downloads or enables X publishing.

## Rights and parent integrity

Every `NormalizedMediaItem` retains one `source_post_id` and media order. A
profile/channel URL is never stored as an individual source post. Cross-parent
text/media mixing is prohibited.

Live Sheets `media_permissions` is the runtime authority. The latest matching
row must be approved, evidence-backed, unexpired, non-revoked, carry an
approved media rights status and enable the exact requested operations. Public
availability, repo metadata or a registered profile does not grant media reuse.

## Geometry and review

Source geometry is preserved by default. `force_9_16` is explicit-only.
`WAITING_REVIEW` cannot be processed by workers; only a human-approved `READY`
row can proceed. Media slots never fall back to text.

## Deferred cleanup

Playwright/browser adapters and historical physical-media paths are inactive
cleanup candidates, not current production dependencies. Do not delete them
until X and YouTube have dual-account physical Goldens and reachability
analysis proves removal safe.
