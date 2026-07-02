# Source Registry Inventory

Generated from `config/source_accounts/default_sources.json` on 2026-07-02. This inventory is review-first: no fetch, download, cut, upload, or post is enabled by this document.

## Summary

- Total source registry rows: 68
- Inventoried Threads/X/YouTube/TikTok/local rows shown below: 61
- Platform counts: {"local": 1, "threads": 7, "tiktok": 9, "x": 16, "youtube": 28}
- `fetch_enabled=true`: 0
- `clip_enabled=true`: 0
- `media_pipeline_eligible=true`: 0
- TODO/placeholders needing human URL or rights review: 5

## Autonomous Mode Source Use

Autonomous mode does not bulk-enable the registry. `fetch_enabled=true` remains 0 in the registry by default. The autonomous loop selects only reviewed pilot source candidates at runtime:

- `src_ns_threads_required_001`
- `src_ns_threads_required_002`
- `src_lm_yt_cand_001`

X, beauty, TODO placeholders, unknown-rights media, and all media-pipeline rows remain excluded. YouTube in the first autonomous scope is metadata/transcript/reference analysis only; no download, cut, upload, or repost is allowed.

## Rights Rules

- `third_party_reference_only`: analysis only. Do not save media bodies, download, cut, upload, or repost.
- `unknown`: blocked until human rights approval.
- `owned`, `licensed`, `approved_creator_clip`: may become media pipeline eligible after permission fields are filled and human review passes.
- X/Threads media remains reference-only. X fetch/post stays off by default.
- TODO placeholders use empty `source_url`; do not replace them with guessed URLs.

## Collection Tool Policy

- `yt_dlp`: main metadata path for YouTube/TikTok; `download=false` for third-party sources.
- `youtube_transcript_api`: transcript path when public/official captions exist; transcript preview/body is not printed.
- `agent_reach`: optional external signal/source discovery only; not production runtime enabled.
- `last30days`: optional external trend/source discovery only; not direct post body generation.
- `tiktok_to_ytdlp`: optional helper for TikTok URL conversion; individual `/video/` URLs are preferred.
- `manual` / `todo`: human-supplied URL/evidence required before collection.

## Sheets Schema Notes

- `source_accounts`: registry master. Current schema has source URL, target accounts, rights/reuse/media policy, fetch/download/cut/upload gates, and manual-only fields.
- `reference_sources`: Sheets-facing source mirror with the same safety gates.
- `source_account_posts`: collected reference rows. Stores metadata/text/media URL references only; third-party media bodies are not saved.
- `media_assets`: media asset records for owned/licensed/approved creator material. Third-party/reference-only media must not enter this table as reusable media.
- `video_references`: no standalone schema is currently defined. Video references flow through `reference_posts`, `video_transcripts`, and `video_clip_candidates`.
- `video_transcripts`: transcript preparation rows.
- `video_clip_candidates`: clip plan rows with rights status, permission status, reuse risk, and cut/upload status fields.

## Inventory

| platform | source_url | source_type | target_account_id | usage_scope | rights_status | fetch_enabled | manual_only | transcript_enabled | clip_enabled | media_pipeline_eligible | collection_method | current_status | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| local | `TODO` | local_file | night_scout,liver_manager | media_asset | unknown | false | true | false | false | false | todo | needs_rights_review | TODO placeholder for owned/licensed/approved_creator_clip media. Human must fill owner, permission evidence, rights_stat |
| threads | https://www.threads.com/@chiikawan400 | account | night_scout | trend_signal | reference_only | false | true | false | false | false | manual | registered | ユーザー共有済みThreads URL（回収）。キャバ/夜職系個人発信。構成・フック・投稿アイデア参照のみ。実download/repost禁止。manual_only（実fetchなし）。 / ユーザー明示required source  |
| threads | https://www.threads.com/@kyaba_oohata | account | night_scout | trend_signal | reference_only | false | true | false | false | false | manual | registered | ユーザー共有済みThreads URL（回収）。キャバ嬢系個人発信。構成・フック・投稿アイデア参照のみ。実download/repost禁止。manual_only（実fetchなし）。 / ユーザー明示required source UR |
| threads | https://www.threads.com/@kyaba_rui_scout | account | night_scout | trend_signal | reference_only | false | true | false | false | false | manual | registered | ユーザー共有済みThreads URL（回収）。スカウト/夜職系個人発信。構成・フック・投稿アイデア参照のみ。実download/repost禁止。manual_only（実fetchなし）。 |
| threads | https://www.threads.com/@kyaba_ryo | account | night_scout | trend_signal | reference_only | false | true | false | false | false | manual | registered | ユーザー明示required source URL。night_scout用Threads参考source。構成・フック・投稿アイデア参照のみ。実fetch/download/repost禁止。manual_only。 |
| threads | https://www.threads.com/@kyabaraunzi | account | night_scout | trend_signal | reference_only | false | true | false | false | false | manual | registered | ユーザー明示required source URL。night_scout用Threads参考source。構成・フック・投稿アイデア参照のみ。実fetch/download/repost禁止。manual_only。 |
| threads | https://www.threads.com/@levi_kyaba | account | night_scout | trend_signal | reference_only | false | true | false | false | false | manual | registered | ユーザー明示required source URL。night_scout用Threads参考source。構成・フック・投稿アイデア参照のみ。実fetch/download/repost禁止。manual_only。 |
| threads | https://www.threads.com/@mizuno9120 | account | night_scout | trend_signal | reference_only | false | true | false | false | false | manual | registered | ユーザー明示required source URL。night_scout用Threads参考source。構成・フック・投稿アイデア参照のみ。実fetch/download/repost禁止。manual_only。 |
| tiktok | https://www.tiktok.com/@coscoslife | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | tiktok_to_ytdlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| tiktok | https://www.tiktok.com/@egachannel1 | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | tiktok_to_ytdlp | registered | beauty_account 永続ブロック。active化不可。 / video reference_only can_reuse_media=false (transcribe/clip-candidate only) / beauty_ |
| tiktok | https://www.tiktok.com/@machimachi_877 | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | tiktok_to_ytdlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| tiktok | https://www.tiktok.com/@miwa_asmr | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | tiktok_to_ytdlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| tiktok | https://www.tiktok.com/@mote_cosme | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | tiktok_to_ytdlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| tiktok | https://www.tiktok.com/@shushu_223_ | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | tiktok_to_ytdlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| tiktok | https://www.tiktok.com/@snam8_ | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | tiktok_to_ytdlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| tiktok | `TODO` | video | liver_manager | clip_candidate | unknown | false | true | false | false | false | todo | needs_human_url | TODO placeholder. Human must provide a real TikTok /video/ URL before dry-run. No fake URL, fetch, download, cut, upload |
| tiktok | `TODO` | video | night_scout | clip_candidate | unknown | false | true | false | false | false | todo | needs_human_url | TODO placeholder. Human must provide a real TikTok /video/ URL before dry-run. No fake URL, fetch, download, cut, upload |
| x | https://x.com/chicoecco | account | beauty_account | trend_signal | reference_only | false | true | false | false | false | manual | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / X refer |
| x | https://x.com/fortune_sachiko | account | beauty_account | trend_signal | reference_only | false | true | false | false | false | manual | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / X refer |
| x | https://x.com/hondayuni | account | beauty_account | trend_signal | reference_only | false | true | false | false | false | manual | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / X refer |
| x | https://x.com/mochi__cosme | account | beauty_account | trend_signal | reference_only | false | true | false | false | false | manual | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / X refer |
| x | https://x.com/saraparin | account | beauty_account | trend_signal | reference_only | false | true | false | false | false | manual | registered | beauty_account 永続ブロック。active化不可。 / X reference-only manual_only (current phase, no posting/dev) / beauty_future: future  |
| x | https://x.com/soi_beauty | account | beauty_account | trend_signal | reference_only | false | true | false | false | false | manual | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / X refer |
| x | https://x.com/meg_lsm | account | liver_manager | trend_signal | reference_only | false | true | false | false | false | manual | registered | 旧repo X_autopost_yoru の monitor_accounts から移行 (2026-06-24)。candidate=WAITING_REVIEW。 / X reference-only manual_only (cur |
| x | https://x.com/ryoyan_1130 | account | liver_manager | trend_signal | reference_only | false | true | false | false | false | manual | registered | 旧repo X_autopost_yoru の monitor_accounts から移行 (2026-06-24)。candidate=WAITING_REVIEW。 / X reference-only manual_only (cur |
| x | https://x.com/1okukure_ | account | night_scout | trend_signal | reference_only | false | true | false | false | false | manual | registered | 旧repo X_autopost_yoru の monitor_accounts から移行 (2026-06-24)。candidate=WAITING_REVIEW。 / X reference-only manual_only (cur |
| x | https://x.com/3j2c9q | account | night_scout | trend_signal | reference_only | false | true | false | false | false | manual | registered | 旧repo X_autopost_yoru の monitor_accounts から移行 (2026-06-24)。candidate=WAITING_REVIEW。 / X reference-only manual_only (cur |
| x | https://x.com/amuxamudaily | account | night_scout | trend_signal | reference_only | false | true | false | false | false | manual | registered | 旧repo X_autopost_yoru の monitor_accounts から移行 (2026-06-24)。candidate=WAITING_REVIEW。 / X reference-only manual_only (cur |
| x | https://x.com/cabalounge | account | night_scout | trend_signal | reference_only | false | true | false | false | false | manual | registered | 旧repo X_autopost_yoru の monitor_accounts から移行 (2026-06-24)。candidate=WAITING_REVIEW。 / X reference-only manual_only (cur |
| x | https://x.com/minatoku789 | account | night_scout | trend_signal | reference_only | false | true | false | false | false | manual | registered | 旧repo X_autopost_yoru の monitor_accounts から移行 (2026-06-24)。candidate=WAITING_REVIEW。 / X reference-only manual_only (cur |
| x | https://x.com/onigiriscout_0 | account | night_scout | trend_signal | reference_only | false | true | false | false | false | manual | registered | 旧repo X_autopost_yoru の monitor_accounts から移行 (2026-06-24)。candidate=WAITING_REVIEW。 / X reference-only manual_only (cur |
| x | https://x.com/takashimaanna | account | night_scout | trend_signal | reference_only | false | true | false | false | false | manual | registered | X text reference only. 構成・フック参照のみ。実download/repost禁止。 / X reference-only manual_only (current phase, no posting/dev) |
| x | https://x.com/urarament | account | night_scout | trend_signal | reference_only | false | true | false | false | false | manual | registered | 旧repo X_autopost_yoru の monitor_accounts から移行 (2026-06-24)。candidate=WAITING_REVIEW。 / X reference-only manual_only (cur |
| youtube | https://www.youtube.com/@775nanako | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | youtube_transcript_api | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@CosmeWotaSara | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | youtube_transcript_api | registered | beauty_account 永続ブロック。active化不可。 / video reference_only can_reuse_media=false (transcribe/clip-candidate only) / beauty_ |
| youtube | https://www.youtube.com/@aratatomori | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | youtube_transcript_api | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@arichan_make | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | youtube_transcript_api | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@fukurena | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | youtube_transcript_api | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@hirobeautychannel | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | youtube_transcript_api | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@saaya3831 | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | youtube_transcript_api | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@shikanoma | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | youtube_transcript_api | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@yui_yanagihashi | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | youtube_transcript_api | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/channel/UCffg7iYU2K7HFJDhylZzUBw | channel | beauty_account | trend_signal | reference_only | false | false | false | false | false | youtube_transcript_api | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | `TODO` | video | liver_manager | clip_candidate | unknown | false | true | false | false | false | todo | needs_human_url | TODO placeholder. Human must provide a real YouTube video URL before dry-run. No fake URL, fetch, download, cut, upload, |
| youtube | https://www.youtube.com/@%E3%83%A9%E3%82%A4%E3%83%90%E3%83%BC%E7%A0%94%E7%A9%B6%E6%89%80%E3%83%A9%E3%82%A4%E3%83%96%E3%83%8A%E3%82%A6 | channel | liver_manager | clip_candidate | unknown | false | false | false | false | false | yt_dlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@amaneri333 | channel | liver_manager | clip_candidate | unknown | false | false | false | false | false | yt_dlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@nanachan7pococha | channel | liver_manager | clip_candidate | unknown | false | false | false | false | false | yt_dlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@suu-san_pococha | channel | liver_manager | clip_candidate | reference_only | false | false | false | false | false | yt_dlp | registered | ユーザー確認済み: YouTube利用可否問題なし (2026-06-24)。 現在は参考利用のみ (reference_only)。 approved_media/own_media 移行にはソース別許諾確認が必要。 / video re |
| youtube | https://www.youtube.com/@yukidora | channel | liver_manager | clip_candidate | unknown | false | false | false | false | false | yt_dlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@yukidora/streams | channel | liver_manager | clip_candidate | unknown | false | false | false | false | false | yt_dlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/playlist?list=PLc2iRTy3vD2ES8qEy3RdcHIavU7AMf8by | playlist | liver_manager | clip_candidate | unknown | false | false | false | false | false | yt_dlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | `TODO` | video | night_scout | clip_candidate | unknown | false | true | false | false | false | todo | needs_human_url | TODO placeholder. Human must provide a real YouTube video URL before dry-run. No fake URL, fetch, download, cut, upload, |
| youtube | https://www.youtube.com/@ClubUNJOURTOKYO | channel | night_scout | clip_candidate | unknown | false | false | false | false | false | yt_dlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@ichijo_hibiki | channel | night_scout | clip_candidate | unknown | false | false | false | false | false | yt_dlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@kyaba_camera/ | channel | night_scout | clip_candidate | unknown | false | false | false | false | false | yt_dlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@miyuchannel1108 | channel | night_scout | clip_candidate | unknown | false | false | false | false | false | yt_dlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@sakuraimizuki | channel | night_scout | clip_candidate | unknown | false | false | false | false | false | yt_dlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/@shingekinoa3485 | channel | night_scout | clip_candidate | unknown | false | false | false | false | false | yt_dlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/channel/UC_GIhz5Cvb1NANQr_QPsnpA | channel | night_scout | clip_candidate | unknown | false | false | false | false | false | yt_dlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/channel/UCbclA18j8r-O1LyzTVpnI-A | channel | night_scout | clip_candidate | unknown | false | false | false | false | false | yt_dlp | registered | User-provided production source candidate. Real fetch/download/cut/upload/post require explicit confirm gates. / video r |
| youtube | https://www.youtube.com/channel/UCh7IsMrygg8X4hEJe8mUcQw | channel | night_scout | clip_candidate | reference_only | false | false | false | false | false | yt_dlp | registered | ユーザー確認済み: YouTube利用可否問題なし (2026-06-24)。 現在は参考利用のみ (reference_only)。 approved_media/own_media 移行にはソース別許諾確認が必要。 / video re |

## Human URL / Rights TODOs

| item_needed | platform | target_account_id | expected_type | notes |
| --- | --- | --- | --- | --- |
| real URL | youtube | night_scout | video | TODO placeholder. Human must provide a real YouTube video URL before dry-run. No fake URL, fetch, download, cut, upload, |
| real URL | youtube | liver_manager | video | TODO placeholder. Human must provide a real YouTube video URL before dry-run. No fake URL, fetch, download, cut, upload, |
| real URL | tiktok | night_scout | video | TODO placeholder. Human must provide a real TikTok /video/ URL before dry-run. No fake URL, fetch, download, cut, upload |
| real URL | tiktok | liver_manager | video | TODO placeholder. Human must provide a real TikTok /video/ URL before dry-run. No fake URL, fetch, download, cut, upload |
| rights evidence and local/source ref | local | night_scout,liver_manager | local_file | TODO placeholder for owned/licensed/approved_creator_clip media. Human must fill owner, permission evidence, rights_stat |

## Owned / Licensed Media Registration Template

Use `config/source_accounts/owned_media_asset_template.json` and `docs/media-rights-template.md` before media ingestion. Required fields include owner/creator, permission source/evidence, permission dates, rights status, allowed/prohibited uses, reviewer, and target account.

## Production Pilot Candidates

These are candidates only. `fetch_enabled=true` remains 0 until a human explicitly runs `prepare_pilot_sources.py --apply --confirm-pilot`.

| account_id | source_id | platform | source_url | current_use |
|---|---|---|---|---|
| `night_scout` | `src_ns_threads_required_001` | threads | `https://www.threads.com/@kyaba_ryo` | reference metadata/text dry-run |
| `night_scout` | `src_ns_threads_required_002` | threads | `https://www.threads.com/@mizuno9120` | reference metadata/text dry-run |
| `liver_manager` | `src_lm_yt_cand_001` | youtube | `https://www.youtube.com/@suu-san_pococha` | metadata/transcript analysis only |

Excluded from pilot: X, `beauty_account`, TODO placeholders, `unknown` rights rows, media download/cut/upload/post.
