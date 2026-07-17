# Source Backend Decision

## Runtime policy

One PRIMARY backend runs for a capability. A FALLBACK runs only after PRIMARY
failure. Router health and routing decisions are saved to `backend_health` and
`backend_routing_history`; neither table stores cookies, browser state, source
text, media URLs, or secrets.

| Capability | PRIMARY | FALLBACK | Status |
| --- | --- | --- | --- |
| YouTube/TikTok profile metadata | `yt-dlp` | none | PRIMARY |
| Threads public profile posts | own public Playwright adapter | own public HTTP adapter | PRIMARY/FALLBACK |
| YouTube transcript | `youtube-transcript-api` | yt-dlp subtitles, local faster-whisper | PRIMARY/FALLBACK |
| Trend signals | local `source_posts` aggregator | none | PRIMARY |
| Agent-Reach/last30days | not a posting or media truth backend | optional analysis shadow only | ANALYSIS_ONLY |

The Threads adapters use a fresh browser context, public HTML only, no stored
cookies, no private GraphQL, no proxy rotation, no stealth/CAPTCHA bypass, and
serial requests. A normal public-page failure opens a 15-minute circuit breaker
and then permits the HTTP fallback.

## Repository audit

Audited on 2026-07-17 against each repository's then-current default branch.
No listed repository is vendored here.

| Candidate | License / implementation observation | Decision |
| --- | --- | --- |
| `yt-dlp/yt-dlp` | Unlicense; active extractor already installed. | PRIMARY for public YouTube/TikTok discovery and approved individual-video download only. |
| `Panniantong/Agent-Reach` | MIT; public-channel discovery plus optional Playwright/browser-cookie integrations. | ANALYSIS_ONLY, never media truth/repost input. |
| `mvanhorn/last30days-skill` | MIT; optional third-party-token integrations. | ANALYSIS_ONLY shadow; local aggregation is production default. |
| `firecrawl/firecrawl` | AGPL-3.0 and self-host needs several services. | REJECTED for the 2GB VPS. |
| `HasData/tiktok-scraping` | paid API/proxy product model. | REJECTED. |
| `Zeeshanahmad4/Threads-Scraper` | MIT; optional cookie/proxy configuration. | ANALYSIS_ONLY reference; no cookie/proxy path is used. |
| `vdite/threads-scraper` | MIT; Playwright login/session-cookie persistence. | REJECTED for production. |
| `galihkjaya/threadscraper` | MIT; token/cookie capture and private GraphQL-oriented workflow. | REJECTED for production. |
| Existing transcript/processing stack | `youtube-transcript-api`, faster-whisper, Playwright, BeautifulSoup, ffmpeg, Cloudinary. | Retained with resource and permission gates. |

## Media ownership boundary

`NormalizedSourcePost` and every `NormalizedMediaItem` carry the same
`source_post_id`; validation rejects mismatched parents. `source_posts` is
deduplicated by source-post ID/canonical post URL, and `source_post_media` by
media ID and `media_index`.

Direct Threads/TikTok/YouTube reuse requires an active, non-revoked
`media_permissions` row with direct download, Cloudinary storage, repost, and
new-caption grants. Threads grants are direct-media-only; approved
YouTube/TikTok sources retain clip permissions. `revoked=true` is never
overwritten.

## Operational limits

- Threads: 5 posts/profile scan, one Chromium process, serial requests.
- YouTube/TikTok: 10 posts/scan, bounded to 3 by production workflows.
- No automatic TikTok profile expansion beyond bounded yt-dlp metadata.
- Mixed carousels require `ALLOW_THREADS_MIXED_CAROUSEL=true` and are false by
  default. Homogeneous carousels use the official Threads container route only
  when `ALLOW_THREADS_CAROUSEL=true` in the scoped apply step.
- `source_videos` must be real discovered records and have real transcripts
  before clip candidates are produced. Dry-run invents neither IDs nor text.
