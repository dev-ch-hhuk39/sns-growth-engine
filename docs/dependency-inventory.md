# Dependency Inventory

Date: 2026-06-30

This inventory separates dependency states:

- `installed`: listed in `requirements.txt` and expected to be available after `pip install -r requirements.txt`.
- `imported`: imported by repo code.
- `wired`: reachable from an existing CLI path.
- `tested`: covered by a script test.
- `optional`: documented candidate, not required for the safe v2 path.
- `rejected`: intentionally not used for this phase.
- `not_found`: no repo integration found.

No secret, token, cookie, browser storage-state content, or API key is documented here.

| tool/library | category | status | current_location | target_script | purpose | risk / ToS note | install_action | next_action |
|---|---|---|---|---|---|---|---|---|
| Agent Reach | external signals | optional | `src/reference/fetchers/agent_reach_fetcher.py`, source registry `collection_method=agent_reach`, docs | `collect_source_posts.py` external signal candidate only | source discovery / shortlist enrichment | non-core CLI; may require logged-in local/browser context; do not use for direct post text generation | none this turn | install only after human confirms source/ToS; keep optional |
| CLI-Anything | external signals | optional / not_found | no repo import; no requirements entry | none | possible external signal runner | unknown provenance/stability | none | do not claim installed unless binary/package exists |
| last30days-skill | external signals | optional / wired | `src/reference/fetchers/last30days_fetcher.py`, docs, source registry | source fetcher path | trend query source | external skill availability/environment dependent | none | keep as optional trend source |
| knowledge-work-plugins | external signals | optional / not_found | docs/search references only, no import | none | possible knowledge tooling | outside repo scope | none | do not wire until concrete package/CLI exists |
| anthropic skills系 | external signals | optional / not_found | docs concept only | none | human/AI workflow helper | not app runtime dependency | none | docs only |
| Understand-Anything | external signals | optional / not_found | no concrete repo import | none | possible analysis tool | unknown package/provenance | none | do not wire |
| CodeGraph | dev tooling | optional | docs only, active MCP in dev environment | none in app runtime | code intelligence | development-only, not production runtime | none | keep out of app requirements |
| Headroom | dev tooling | optional | docs only | none in app runtime | LLM cost/proxy tool | development-only | none | keep out of app requirements |
| Threads Scraper系 | Threads | optional / rejected | not in requirements; no concrete package import | none | direct Threads scrape | non-official ToS/stability risk | none | use public OG / official API first |
| Playwright | Threads | installed / imported / wired / tested | `requirements.txt`, `collect_threads_metrics.py` | `collect_threads_metrics.py --source browser --browser-engine playwright` | browser fallback for metrics page checks | login storage state must not be printed; browser binaries may be missing | added to requirements | use only dry-run until legal/ops reviewed |
| BeautifulSoup4 | parsing | installed / imported / wired / tested | `requirements.txt`, `collect_source_posts.py` | `collect_source_posts.py` | stable OG metadata parsing | public HTML only | added to requirements | default parser when installed |
| lxml | parsing | installed / wired / tested | `requirements.txt`, parser selected by BS4 | `collect_source_posts.py` | faster/stricter HTML parser | parser dependency only | added to requirements | fallback to html.parser when absent |
| requests | HTTP | installed / imported / wired | `requirements.txt`, publishers/media/llm | existing publishers/media clients | HTTP API calls | secrets must not be printed | existing | continue guarded use |
| tweepy | X | installed / optional / tested | `requirements.txt`, publisher tests, X fetch skeleton | `collect_source_posts.py` X plan only | possible X fetch/post library | X API credit/ToS risk; X fetch/post OFF | existing | no X fetch this phase |
| twikit | X | optional / not_found | no import | none | unofficial X access | ToS/stability risk | none | do not add |
| snscrape | X | optional / not_found | no import | none | unofficial X scraping | maintenance/ToS risk | none | do not add |
| X API / Twitter API | X | optional / wired for posting only | publisher docs/scripts | X publisher only, fetch OFF | X posting/fetch | credits depleted risk; fetch not enabled | existing guarded path | keep fetch/post disabled |
| Threads official API | Threads | optional | `src/publishers/threads_publisher.py` for posting | metrics/source fetch not yet official-wired | official Threads operations | API capability/permissions may not expose metrics | none | prefer official API for future metrics |
| Threads public HTML/OG metadata | Threads | imported / wired / tested | `collect_threads_metrics.py`, `collect_source_posts.py` | metrics/source collection | public metadata and best-effort metrics | metrics may be hidden; unknown stays null | stdlib + BS4/lxml | keep as safe fallback |
| yt-dlp | video metadata | installed / imported / wired / tested | `requirements.txt`, `collect_video_references.py`, existing fetchers | `collect_video_references.py --metadata-adapter yt-dlp` | YouTube/TikTok metadata only | do not download third-party media | added to requirements | keep `download=False` |
| tiktok-to-ytdlp | TikTok | optional / imported adapter docs | `src/reference/fetchers/tiktok_to_ytdlp_fetcher.py` | source fetcher path | TikTok URL conversion | external CLI availability | none | optional only |
| TikTokApi | TikTok | optional / not_found | no import | none | TikTok metadata | unofficial/fragile | none | do not add |
| pytube系 | YouTube | optional / not_found | no import | none | YouTube metadata | maintenance/stability | none | prefer yt-dlp/API |
| YouTube Data API / google-api-python-client | YouTube | optional / not_found | no import | none | official YouTube metadata | API key/quota required | none | optional after credentials review |
| youtube-transcript-api | transcript | installed / imported / wired / tested | `requirements.txt`, `collect_video_references.py`, `transcribe_video_reference.py` | transcript adapters | official/public transcript when available | transcript may be unavailable; no video download | added to requirements | use only transcript text |
| ffmpeg CLI | media | optional / wired / tested | `src/video/clip_cutter.py`, `cut_approved_clips.py` | cut approved clips | owned/licensed clip cutting | local binary dependent; third-party cut blocked | no pip action | install system ffmpeg separately if needed |
| ffmpeg-python | media | installed / wired / tested | `requirements.txt`, `cut_approved_clips.py` status | cut planning/status | Python wrapper status check | does not provide ffmpeg binary | added to requirements | use only with rights/env gates |
| moviepy | media | optional / not_found | no import | none | video editing | heavy dependency | none | do not add |
| pydub | audio | optional / not_found | no import | none | audio processing | ffmpeg dependency | none | do not add |
| whisper | transcription | optional | Cloudflare Whisper client docs only | none local | transcription | heavy/local model or external API | none | keep external API gated |
| faster-whisper | transcription | optional / not_found | no import | none | local transcription | heavy model/runtime | none | do not add |
| OpenAI/外部transcription API | transcription | optional / wired gate | `transcribe_video_reference.py`, transcription docs | transcription delegate | external transcription | API cost/privacy; requires env + confirm | none | gated only |
| PaddleOCR | OCR | optional / not_found | no import | none | OCR | heavy dependency | none | do not add |
| VoxCPM | audio/video | optional / not_found | no import | none | advanced media analysis | heavy/unclear | none | do not add |
| Cloudinary SDK | cloud | installed / imported / wired / tested | `requirements.txt`, `upload_media_assets.py`, media docs | `upload_media_assets.py` | upload adapter status and future SDK path | upload gated by env + confirm; third-party blocked | added to requirements | dry-run validation only |
| Pillow | media | installed | `requirements.txt` | future media/image checks | image metadata/validation | local file handling only | added to requirements | wire when image processing is needed |
| Google Drive / Sheets | storage | installed / imported / wired | `requirements.txt`, `src/sheets_client.py` | Sheets-backed CLIs | persistent registry/queue/results | API quotas; secrets never printed | existing | continue verify-first |
| storage/archive関連 | storage | imported / wired | archive scripts/docs | archive reference data | redacted raw preservation | never store secrets/cookies | existing | keep redaction tests |
| MoneyPrinterTurbo | video generation | optional / rejected | docs/search mention only | none | automated video generation | out of scope, copyright/quality risk | none | do not add |
| ViMax | video generation | optional / rejected | no concrete repo import | none | automated video generation | out of scope/provenance risk | none | do not add |

## Agent Reach Clarification

Agent Reach is not a runtime dependency of the current v2 production loop.

- repo presence: yes, `src/reference/fetchers/agent_reach_fetcher.py` and source registry `collection_method=agent_reach`.
- requirements presence: no.
- import presence: local fetcher code only; not imported by `collect_source_posts.py` as a hard dependency.
- execution CLI presence: optional fetcher can check `agent-reach` / `npx agent-reach`, but this turn did not install or run it.
- current usable state: optional only unless the local CLI is installed and human confirms ToS/session handling.
- missing for production use: explicit install source, local login/session policy, terms review, and source ranking acceptance criteria.
- not to confuse with: any separate Library Scout or other project-level plugin. This repo does not currently vendor such a system.

Agent Reach, if later enabled, should feed source discovery, external signals, repo/library reputation, and account/source shortlist enrichment only. It must not directly generate SNS post body copy.

## CLI-Anything Clarification

CLI-Anything is not installed, imported, or wired in this repo. It is documented as an optional candidate only. Do not report it as available unless a concrete binary/package and adapter are added.

## Environment Verification (2026-07-01)

`pip install -r requirements.txt` completed successfully after network approval.

Import check:

- OK: `bs4`, `lxml`, `playwright`, `yt_dlp`, `youtube_transcript_api`, `PIL`, `ffmpeg`, `cloudinary`.

Playwright:

- `python3 -m playwright install chromium` exited with code 0.
- `collect_threads_metrics.py --source browser --browser-engine playwright` ran in dry-run and returned `UNAVAILABLE` / `playwright_no_metrics` for the two live Threads post URLs. Unknown metrics stayed null.

Media:

- `cut_approved_clips.py --rights-status third_party_reference_only` reports `ffmpeg_cli=installed`, `ffmpeg_python=installed`, and blocks cutting.
- `upload_media_assets.py --dry-run` reports `cloudinary=installed` and blocks third-party/reference-only upload.

## Rights-Aware Media Ingestion (2026-07-01)

- Added `src/media/rights_policy.py` as the shared decision table for media workflows.
- Added `scripts/ingest_media_assets.py` for approved media planning. It does not download URL inputs and does not upload to Cloudinary.
- `cut_approved_clips.py`, `upload_media_assets.py`, `collect_video_references.py`, `collect_source_posts.py`, and `generate_media_post_queue.py` now align to `owned/licensed/approved_creator_clip` as the only media-use statuses.
- No new external dependency was added for this rights layer.
