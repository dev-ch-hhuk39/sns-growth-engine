# Agent Reach Optional Reference Backend

## Verified role

Agent Reach 1.5.0 is an installer, doctor, channel selector, and router for
upstream tools. It is not a universal social-post scraper and does not expose
an `agent-reach fetch` command. This repository uses the official
`agent_reach.channels.web.WebChannel` only as an optional, bounded,
analysis-only reference reader.

The exact upstream revision is pinned in `requirements-oss.txt`. A local
operator may also install it outside the repository in
`~/.agent-reach-venv`. The adapter works when either the package is installed
in the current Python runtime or that isolated venv exists. Its absence must
not fail core repository tests or the canonical acquisition routes.

## Measured platform boundary

| Platform | Agent Reach capability | Repository role |
|---|---|---|
| X | Native channel delegates to twitter-cli/OpenCLI and requires explicit login cookies/session | Not used for production discovery; generic fetch is blocked |
| YouTube | Native yt-dlp readiness, metadata, subtitles/transcript availability | Shadow/readiness only; canonical yt-dlp route stays primary |
| Threads | No native channel | Generic Web/Jina profile reference only; not profile discovery or physical media |
| TikTok | No native channel | Generic Web/Jina profile reference only; not profile discovery or physical media |
| Instagram/Facebook | Native OpenCLI channel, logged-in Chrome required | Optional future reference backend only |
| Reddit | Native OpenCLI/rdt-cli channel, login required | Optional future reference backend only |
| Xiaohongshu/LinkedIn | Native configured channels with external tools/login | Optional future reference backend only |
| Bilibili | Native public-search fallback | Optional future reference backend only |
| Web/RSS | Native zero-credential readers | Optional bounded research |
| GitHub | Native gh CLI readiness; authentication required for private access | Optional source research |

README sponsor text or a generic web success is not evidence of a native
Threads/TikTok channel. Generic profile text also does not prove individual
post discovery, media ordering, or physical acquisition.

## Safety and routing

- `confirm_fetch=True` is required for a real generic-web read.
- X generic network fetch remains blocked in `AgentReachFetcher`.
- No browser login, cookie extraction, storage state, download, upload, or
  publisher path is present in this adapter.
- Output is at most one bounded web-page snapshot and is normalized through
  `JsonImportFetcher`.
- Canonical physical media remains X/YouTube through yt-dlp after the shared
  permission and provenance gates.
- Threads physical media remains unverified. TikTok physical media now uses
  the canonical public-embed route; Agent Reach remains analysis-only and is
  not part of that physical path.

See `docs/reference-first-media-core-20260811.md` and
`config/source_backend_routing.json` for the canonical architecture.
