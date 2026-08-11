# Agent Reach Capability Audit

Audit date: 2026-08-11 JST

Official source: `Panniantong/Agent-Reach` commit
`1221ecd0c3e0502ee37406f03543bedf7503f2c7`, Agent Reach 1.5.0.
It was installed only in the isolated user-home environment
`~/.agent-reach-venv`. No system package, browser login, cookie extraction, or
repository vendoring was performed.

## Measured Status

Before this audit the repository contained an adapter and configuration, but
the runtime was absent, so its state was `CONFIG_PLACEHOLDER_ONLY`. After the
isolated install and live adapter probes, its state is `INSTALLED_AND_ACTIVE`
for the narrow generic-Web analysis role.

`agent-reach doctor` reported 4 usable channels out of 15: Web/Jina, RSS,
Bilibili public search, and V2EX. Optional channels remain unavailable until
their own upstream CLI or authentication requirements are met.

## Platform Matrix

| Platform | Classification | Measured result | Recommended role |
|---|---|---|---|
| X / Twitter | NATIVE_CONFIG_REQUIRED | Native route requires explicit login/cookie; Jina profile probe returned HTTP 403 | NOT_USED until explicit auth; existing gallery-dl metadata and yt-dlp physical routes remain canonical |
| YouTube | NATIVE_CONFIG_REQUIRED | Agent Reach delegates to yt-dlp; direct upstream yt-dlp metadata and Japanese captions passed for both managed accounts | SHADOW readiness only; existing yt-dlp/transcript route remains PRIMARY |
| Threads | GENERIC_WEB_ONLY | Public profile text was readable, but no individual `/post/` discovery or physical media | ANALYSIS_ONLY |
| TikTok | GENERIC_WEB_ONLY | Public profile text was readable, but no individual `/video/` discovery or physical media | ANALYSIS_ONLY |
| Instagram | NATIVE_CONFIG_REQUIRED | Optional upstream CLI/login not configured | OPTIONAL_REFERENCE_BACKEND |
| Facebook | NATIVE_CONFIG_REQUIRED | Optional upstream CLI/login not configured | OPTIONAL_REFERENCE_BACKEND |
| Reddit | NATIVE_CONFIG_REQUIRED | Optional upstream route not configured | OPTIONAL_REFERENCE_BACKEND |
| Xiaohongshu | NATIVE_CONFIG_REQUIRED | Optional upstream CLI/session not configured | OPTIONAL_REFERENCE_BACKEND |
| LinkedIn | NATIVE_CONFIG_REQUIRED | Optional upstream CLI/session not configured | OPTIONAL_REFERENCE_BACKEND |
| Bilibili | NATIVE_ZERO_CONFIG | Doctor public-search check passed | OPTIONAL_REFERENCE_BACKEND |
| Web | NATIVE_ZERO_CONFIG | Jina WebChannel passed | ANALYSIS_ONLY |
| RSS | NATIVE_ZERO_CONFIG | Doctor check passed | OPTIONAL_REFERENCE_BACKEND |
| GitHub | NATIVE_CONFIG_REQUIRED | `gh` was detected; live auth was not asserted by doctor | OPTIONAL_REFERENCE_BACKEND |

Agent Reach has no native Threads or TikTok channel in this audited upstream.
README or sponsor references to a platform are not treated as channel support.

## Bounded Live Probes

- X: `https://x.com/meg_lsm` through Web/Jina returned HTTP 403. Native X
  remains `AUTH_REQUIRED`. No cookies were requested or extracted.
- YouTube: Night Scout channel discovery selected `A3DeaGlHwxQ` and fetched
  metadata plus 266 Japanese caption events. Liver Manager selected
  `mncisIwoo_I` and fetched metadata plus 500 Japanese caption events. No media
  was downloaded.
- Threads: `@me01_lsm` and `@chiishunin_s` profile pages were readable as
  generic Web text, but no individual post URLs were discovered.
- TikTok: `@user5597696107300` profile text was readable as generic Web text,
  but no individual video URL was discovered.

## Canonical Architecture Decision

The reference discovery priority remains TikTok, Threads, X, then YouTube.
Physical media remains X and YouTube through yt-dlp. Threads and TikTok
physical acquisition remain deferred. Agent Reach does not replace the
acquisition router and does not activate Playwright/browser/session paths.

The repository adapter is fail-optional and analysis-only. Environments without
Agent Reach continue to pass core tests, while the isolated runtime can provide
bounded generic-Web reference text when available.
