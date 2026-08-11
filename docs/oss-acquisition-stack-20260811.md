# OSS acquisition stack audit (2026-08-11)

## Decision

The production stack is capability-oriented. It does not install one scraper
per platform and does not assume one backend can discover profiles, resolve
posts, download media and collect comments. Runtime selection is described by
`config/acquisition_backend_capabilities.json` and validated before the router
starts.

Production rules are fixed: backend-only, bounded, read-only acquisition; no
automatic cookie extraction; no browser runtime; no opaque downloader service;
no fallback around author, rights, private-source or third-party-repost blocks.
Missing optional tools fail soft. `scripts/acquisition_doctor.py --json` reads no
credentials and performs no network or production writes.

## Adopted stack

| Capability | Primary | Fallback / shadow | Current result |
|---|---|---|---|
| X exact-status physical media | yt-dlp 2026.7.4 | none | 4/4 prior live A/V goldens; unchanged |
| X bounded profile metadata | gallery-dl 1.32.9 | manual JSON/browser export only after explicit failure | public-or-explicit-auth per source |
| YouTube channel/video/physical | yt-dlp 2026.7.4 | none | 2/2 live A/V goldens and exact owner permission PASS |
| YouTube comments | youtube-comment-downloader 0.1.78 | none | installed and dependency-pinned |
| YouTube transcript | youtube-transcript-api 1.2.4 | yt-dlp subtitles, gated local faster-whisper | source-caption dependent |
| Research | local aggregation | Agent Reach 1.5.0 shadow | Agent Reach measured 4/15 channels |
| TikTok profile posts | internal public embed parser | gallery-dl | 3/3 registered profiles, 9/9 bounded individual posts in live probe |
| TikTok approved physical media | public embed direct HTTP | yt-dlp individual-post fallback | 12,310,033-byte A/V Golden; permission, author and review gates PASS |
| Threads public profile posts | internal public HTTP | bounded search-index, official Graph OPTIONAL_AUTH | zero-auth profile payload/search unresolved; official Graph fixture contract ready |
| Threads individual post detail | official tokenless oEmbed | public HTTP parser | live canonical URL/author/text PASS; physical media not exposed in tested response |

`twscrape` is OPTIONAL_AUTH only (`auth_token` and `ct0`); it does not replace
working X physical acquisition. Browser Threads/TikTok tools and remote
download-conversion websites are not selectable by production routing.

## Candidate audit

The SHAs below are the upstream heads cloned read-only under
`~/.sns-growth-engine-tools/audit-20260811`. Maintenance means upstream activity
observed in 2025-2026. Capability claims were checked against code/manifests,
not README text alone.

| Candidate / tested revision | License | Runtime and dependency boundary | Useful capability | Live/structural result | Decision |
|---|---|---|---|---|---|
| yt-dlp/yt-dlp `5d6b8c8cd19785c3086ae3a9ec618c45e25eb3bc` | Unlicense | Python/CLI; no browser; site-dependent anonymous access | profile/post/detail, formats, subtitles, physical media; its public TikTok embed model informed an independent bounded parser | X and YouTube physical goldens pass; TikTok profile traversal itself stops at secondary user identity, while the public embed payload succeeds | PRIMARY X/YouTube/detail; protocol source for TikTok embed parser |
| mikf/gallery-dl `86047cf67a12bdb6ff1085774f8ad9fc347e8da9` | GPL-2.0-only | Python/CLI; no browser; some extractors conditionally require cookies | X/TikTok metadata and ordered media | X bounded adapter proven by contract; registered TikTok profiles returned no individual posts | PRIMARY X / FALLBACK TikTok |
| egbertbouman/youtube-comment-downloader `9771beeb5be3c9648af011fe10cd813187550db0` | MIT | Python requests; no login/browser | bounded public comments/replies | 0.1.78 installed and pinned | PRIMARY comments |
| Panniantong/Agent-Reach `1221ecd0c3e0502ee37406f03543bedf7503f2c7` | MIT | isolated Python; channel-specific dependencies | YouTube/Web/RSS/GitHub/reference research | 4/15 channels measured; no native Threads/TikTok physical route | SHADOW / ANALYSIS_ONLY |
| vladkens/twscrape `9745b021d8a7405bed8bc56a725813367b3f07dd` | MIT | Python/httpx; X account cookies `auth_token` + `ct0` or credentials | structured timeline/search/metrics/media metadata | no anonymous production route; no credentials collected | OPTIONAL_AUTH |
| hasyaapp/threads-scraper `9cc7055c8ef45779d1c468378e3f6d03778c058b` | MIT | Tampermonkey and rendered DOM | post IDs/text/media/metrics visible to a browser | extraction requires browser page state | BENCHMARK_ONLY |
| Zeeshanahmad4/Threads-Scraper `a6ae79156df2b8a4ee56b8dfb1343101a2641b86` | NOASSERTION | Python Playwright | rendered profile/post extraction | browser required and license unclear | BENCHMARK_ONLY |
| vdite/threads-scraper `feed562e321673693cb477651ec75c816b5e0eac` | MIT | Python Playwright; optional saved session cookies | post/reply GraphQL response observation | browser required; enhanced mode stores session cookies | BENCHMARK_ONLY |
| galihkjaya/threadscraper `2bde447ebbdfabe45198e6267929e60930a9eebc` | MIT in pyproject | Python Playwright; captures `lsd`, csrf/mid cookies | GraphQL response observation | browser/cookie required | BENCHMARK_ONLY |
| milancodess/universalDownloader `a82317b57dfa44320e99ae2a4b7ad18df6dbaa4f` | NOASSERTION | Node/axios; calls lovethreads.net and ssstik.io | individual URL media conversion | opaque third-party services and weak provenance | REJECT |
| ssut/tiktok-api `074c6eea549b9109142e90b09999ece626031a8e` | ISC in manifest | Node; self-contained X-Bogus/X-Gnarly; generated msToken | profile/posts/detail/comments/formats | bounded live probe retried 10 times then `API_EMPTY_RESPONSE`; no secUid | BENCHMARK_ONLY |
| Johnserf-Seed/TikTokDownload `64acbfda8621563da97ed06f133330c3335b1e8d` | MIT | Python; cookie/login and signature machinery; inactive since 2024 | profile/batch physical media | stable use requires account state; old lineage, not the f2/Joean project | REJECT |
| Johnserf-Seed/f2 `7dab3e2ffffaa2535834d28fca99dbc2e89fa9d3` | Apache-2.0 | Python/httpx; generated device data but stable TikTok profile download requires cookie | profile/posts/detail/comments/download | browser-cookie helper exists; no cookie was read; safe anonymous stability not established | OPTIONAL_AUTH |
| Q-Bukold/TikTok-Content-Scraper `5713c1abd2f18aee79972326864922cfbc4c56ea` | NOASSERTION | Python requests plus browser_cookie3 | batch/backfill metadata/media | explicitly imports browser cookies for stable runs; license unclear | BENCHMARK_ONLY |
| MEOMcGill/pytok `e3be73580dc6ca9197a319f0c6c19b7d17f3afee` | NOASSERTION | Playwright persistent profile/login | broad research collection | browser/login required | BENCHMARK_ONLY |
| dfreelon/pyktok `cb6e2eacd046fcb273fe6fcda31835dbcd5cf03f` | BSD-3-Clause | Python Selenium/browser cookies | metadata/video helper | browser route conflicts with owner policy | BENCHMARK_ONLY |
| davidteather/TikTok-Api `4993fe4698acd4d9e495b1c41cec8ffee8b43be9` | MIT | Python Playwright/msToken | profile/posts/comments/search | browser/msToken sensitive | BENCHMARK_ONLY |
| TobyG74/tiktok-api-dl `cbe40b6f0c8bbbec8e6124be2a28dd7153b71192` | Apache-2.0 API metadata | Node; TikTok cookie plus unofficial external API | posts/comments/download | external service and login-cookie path are not acceptable production dependencies | REJECT |
| housine35/tiktok-scraper `dbabd3779a0c6b11b3d96e1dea9efafdaf50892e` | NOASSERTION | Node/Python/Playwright; repository contains hard-coded session material | profile/follower experimentation | security/privacy and license failure | REJECT |
| N4rr34n6/TikTok-User-Info-Scraper `b8592a5ed035482e4d7ff15b274be34458aac508` | AGPL-3.0 | Python requests/HTML regex | profile identity only | no post discovery or physical media | ANALYSIS_ONLY |
| jpfefferlab/tiktokscraper `7d0885d7d5faac1cafb120b8a774400470c6bee3` | MIT | requests for detail; Selenium/login for user videos | individual metadata/comments/profile | missing profile-to-post capability is browser-only | ANALYSIS_ONLY |
| JBGruber/traktok `b04aa36ec949c88266c6b8513c4e07ac7a4ee06f` | GPL-3.0-only | R; hidden/research API | analysis datasets | no deterministic physical-media production adapter | ANALYSIS_ONLY |
| JoeanAmier/TikTokDownloader (DouK-Downloader) `463031d12c42d2b6ddba0f80ef41cb724636c6c4` | GPL-3.0-only | Python 3.12; X-Bogus/msToken/device support; documented TikTok cookie input | comprehensive profile/batch/download | actively maintained but cookie required for production stability | OPTIONAL_AUTH |
| Evil0ctal/Douyin_TikTok_Download_API `42784ffc83a72a516bfe952153ad7e2a3998d16c` | Apache-2.0 | Python API server, signature/cookie management, browser-cookie extension | broad TikTok/Douyin API | too broad and credential-heavy; hosted demo is an external service | BENCHMARK_ONLY |

No candidate code with an unclear or incompatible license was copied into the
application. Public-page behavior was independently probed with the internal
HTTP adapter.

## Live blockers, by backend

### TikTok

Authorized profiles used: `@user5597696107300`, `@me02_lsm`, and `@uare.inc`.

- `tiktok_public_embed` independently parses the public
  `__FRONTITY_CONNECT_STATE__` payload exposed by TikTok's bounded embed page.
  It requires the payload author and every post author to match the registered
  handle, excludes private/malformed entries, caps discovery at 20 and stores
  canonical individual `/video/<id>` URLs with their exact direct media child.
- Live production-route probe passed for all three registered profiles: three
  posts per source, nine posts and nine same-parent video children total. No
  browser, cookies, login or opaque service was used.
- Exact Golden: `src_lm_tt_user_001`,
  `https://www.tiktok.com/@user5597696107300/video/7649682547588254994`.
  The permission ledger and registered-author checks passed; direct public CDN
  acquisition produced 12,310,033 bytes with one 720x1280 video stream, one
  audio stream and 90.950998 seconds duration. The shared path reached
  `WAITING_REVIEW`; publisher eligibility remained false.

- yt-dlp 2026.7.4: profile candidate traversal reaches TikTok extraction but
  fails before canonical post normalization (`secondary user ID` unavailable).
- gallery-dl 1.32.9: bounded metadata route yields no usable individual post.
- ssut/tiktok-api 1.5.2: isolated build succeeds; anonymous live `getUser`
  performs ten library retries and returns `API_EMPTY_RESPONSE`; no secUid.
- f2 and JoeanAmier: current source explicitly requires a TikTok cookie for
  stable profile/post acquisition. They remain disabled `COOKIE_REQUIRED`.
- browser-heavy and external-service tools are policy-ineligible.

The anonymous public route is complete for the currently registered sources.
Cookie-based tools remain disabled optional fallbacks, not a runtime
requirement. Physical reuse remains source-specific: an unregistered author,
missing/revoked permission, private post or third-party repost is fail-closed.

### Threads

Authorized profiles probed: Night Scout `@chiishunin_s`, Liver Manager
`@me01_lsm`. Both returned HTTP 200 transport responses of about 256 KB, but the
SSR payload selected `Barcelona404ErrorRoot`, contained neither handle nor
individual `/post/` links, and exposed no post hydration data to the logged-out
backend client. The browser OSS candidates only recover data from rendered or
authenticated browser GraphQL traffic. The opaque lovethreads converter was
rejected.

Thus public transport reachability is not reported as post discovery. Live
rechecks classify Night Scout `@chiishunin_s` and Liver Manager `@me01_lsm` as
`POST_DISCOVERY_UNAVAILABLE` with exact reasons
`threads_profile_application_404:<handle>`. The minimal external requirement is
a supported backend-only public response from Meta, or a later explicit owner
decision for a dedicated non-personal authenticated acquisition account.
Browser/session automation is not activated.

The v21 official API audit confirmed documented Meta endpoints for public
profile lookup, profile posts and keyword search. They expose canonical IDs,
permalink, username, text, timestamp, media type/URL/thumbnail and ordered
children. This route requires a Threads user access token from a dedicated Meta
developer app, `threads_profile_discovery` for profile discovery and
`threads_keyword_search` for keyword search; advanced access/app review is an
external authorization step. `threads_graph_public_discovery` implements the
bounded optional-auth contract and reports `AUTH_REQUIRED` without a token.

The official `facebook/meta-embeds-for-wordpress` contract also confirms the
tokenless `graph.threads.com/oembed` individual-post route. The implemented
`threads_oembed_detail` adapter passed a live read of one existing public post:
canonical URL, author and text were returned. Its response exposed no direct
physical media, so no thumbnail/embed iframe was promoted to video. A bounded
DuckDuckGo/Bing index probe for registered source handles returned no canonical
post candidate; zero-auth profile-to-permalink discovery therefore remains the
single Threads external gap. Search hits, if later returned, are candidate-only
and must pass exact-author oEmbed validation.

## YouTube exact permission activation

The owner decision in `config/youtube_source_permissions_20260811.json` covers
only `src_ns_yt_cand_006/@ichijo_hibiki` and
`src_lm_yt_cand_001/@suu-san_pococha`. Production `media_permissions` apply
completed with one append and one update; read-after-write was `PASS`, invalid
rows were zero, and every download/storage/repost/transcript/analysis/cut/clip/
caption/edit flag was true. Re-verification of the existing physical files
produced two A/V PASS rows and two `WAITING_REVIEW` candidates with
`publisher_eligible=false`. No other YouTube source inherits this grant.

## Optional future platform matrix

| Platform | Reference discovery | Post/media | Auth | Recommendation |
|---|---|---|---|---|
| Instagram | not active | not active | generally required | Agent Reach analysis only; add no source without owner input |
| Facebook | not active | not active | required | no production backend selected |
| Reddit | Agent Reach optional | text/reference only | public or optional token | Agent Reach shadow |
| Xiaohongshu | Agent Reach optional | analysis only | channel dependent | keep optional; no browser activation |
| LinkedIn | Agent Reach optional | analysis only | generally required | optional auth only |
| Bilibili | Agent Reach optional | metadata/reference | public varies | Agent Reach shadow, yt-dlp only for approved individual media |
| RSS | Agent Reach/local | text/reference | no | safe analysis source after explicit registration |
| Web | Agent Reach/local HTTP | text/reference | no/varies | bounded public HTTP |
| GitHub | Agent Reach/GitHub public | repository/reference | public/token optional | analysis only |

## Upgrade procedure

1. Clone upstream outside the repository and record canonical URL, SHA,
   release, SPDX, runtime/auth/browser/external-service boundaries.
2. Run a bounded anonymous probe against an authorized source. Never read local
   browser cookies.
3. Update the capability registry and exact requirements pin.
4. Add deterministic fixtures and focused route/fail-closed tests.
5. Run `python3 scripts/acquisition_doctor.py --json`, full regression, workflow
   safety and completion evaluator before changing a production role.

Production publishing, Cloudinary upload and Sheets mutation are outside this
audit and were not performed.
