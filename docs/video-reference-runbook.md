# Video Reference Runbook

## 2026-07-12 Transcript-Grounded Media Growth

Approved video operation now has account-separated schedules:

- `Production Autopilot Aftercare` (JST 23:40): bounded discovery into `source_videos`.
- `Media Transcription Production` (JST 00:10): approved individual video URL transcription into `video_transcripts`.
- `Media Growth Production` (JST 09:20): one transcript-grounded approved `liver_manager` video post at most.
- `Media Growth Production Night Scout` (JST 12:20): one transcript-grounded approved `night_scout` video post at most.

The source-level permission record is authoritative. The four registered `liver_manager` YouTube/TikTok sources and nine registered `night_scout` YouTube sources have `approved_creator_clip`, `permission_status=approved`, and `media_autopilot_enabled=true`. Each may be used for bounded discovery, download, transcription, analysis, vertical clipping, Cloudinary storage, Threads reposting, and post-performance analysis. The Night Scout TikTok TODO has no URL and stays excluded.

Transcription rules:

- Only `owned`, `licensed`, or `approved_creator_clip` rows with `permission_status=approved` are eligible.
- Only individual video URLs from `source_videos` are transcribed. Channel/account URLs are discovery sources, not direct transcription/download targets.
- YouTube official/public captions are tried first via `youtube-transcript-api`.
- If captions are unavailable, the workflow may use local `faster-whisper` only when `ALLOW_LOCAL_TRANSCRIPTION=true` and `ALLOW_VIDEO_DOWNLOAD=true` are scoped to the transcription step.
- `ALLOW_TRANSCRIPTION_API=false` remains false; no external transcription API is enabled.
- Transcript text is saved to `video_transcripts.transcript_text`, but logs only show counts/status/short redacted preview.

Clip generation rules:

- `run_media_growth_engine.py` reads `video_transcripts`.
- A source video without DONE transcript becomes `TRANSCRIPT_PENDING` and does not produce READY clips.
- READY/AUTO_APPROVED clip candidates must have `transcript_grounded=true` and `transcript_id`.
- `run_media_production_pipeline.py` blocks old duration-only candidates with `transcript_grounding_required`.

## 2026-07-11 Approved Media Production

Approved channel/account discovery is bounded by `max_videos_per_source_scan`, `max_new_videos_per_source_per_run`, and `max_total_new_videos_per_run`. Discovery uses metadata only and does not download media. It resolves individual canonical URLs and enriches duration metadata before clip planning. TikTok profile discovery remains bounded; it is never an unbounded profile scrape.

Only real discovered IDs are eligible. `PLANNED_ONLY` rows, fake candidate titles, invalid YouTube IDs, and invalid TikTok IDs are excluded from production selection. Distinct clip candidates from one source video are allowed, while an already posted `clip_candidate_id` is skipped.

The scheduled production chains are active only for their explicitly approved account sources. They perform no transcription API call, never include internal analysis in the post text, and require `final_public_post_validator` plus the media validator before publication. A post always uses newly generated `public_post_text`; source titles, URLs, transcript bodies, and internal analysis never enter the published caption.

Date: 2026-06-28

第三者動画を「参考」として安全に扱うための標準 CLI 入口（メタ整理 → 文字起こし）。
download / 切り抜き実行はしない。本 doc は薄い入口で、詳細は既存 doc を参照する。

## 標準 CLI

| CLI | 役割 | 既定 |
|---|---|---|
| `prepare_video_reference.py` | 動画メタ + 切り抜き候補プラン | PLAN_ONLY |
| `transcribe_video_reference.py` | 文字起こし | モック（実 API はゲート） |

## 1. 動画参考の準備

```bash
python3 scripts/prepare_video_reference.py --account-id liver_manager --platform threads --source-platform youtube --video-url <url>
```

- 主要フラグ: `--account-id` / `--platform`（既定 threads） / `--source-platform`（既定 youtube） / `--video-url` / `--source-id` / `--apply` / `--confirm-prepare`。
- 既定はメタ + 切り抜き候補プランのみ。
- download は `--allow-download` かつ `--confirm-download` の二重ゲート（既定 false / 本開発中は実行しない）。
- 書き込み先タブ: `video_transcripts`（準備行） / `video_clip_candidates`（候補プラン）。

## 2. 文字起こし

```bash
python3 scripts/transcribe_video_reference.py --account-id liver_manager --limit 5
# 実 API 文字起こし（env と CLI の二重ゲート）
ALLOW_TRANSCRIPTION_API=true python3 scripts/transcribe_video_reference.py --account-id liver_manager --apply --confirm-transcribe --allow-real-transcription
```

- 主要フラグ: `--account-id` / `--limit`（既定 10） / `--apply` / `--confirm-transcribe` / `--allow-real-transcription`。
- 実 API は `ALLOW_TRANSCRIPTION_API=true`（env）かつ `--allow-real-transcription` の両方が必要。既定はモック。
- 結果は `video_transcripts` に保存。実行履歴は `transcription_runs`。

## 動画ソース管理

動画ソースは `source_accounts` / `reference_sources` で config 駆動管理する（専用 `video_sources` タブは無い）。
登録は [source-collection-runbook.md](source-collection-runbook.md) の `import_reference_urls.py` を参照。

## 安全方針

- 第三者動画は参考分析・メタ・文字起こし・切り抜き候補化まで。実 download / ffmpeg cut / Cloudinary upload はしない。
- `media_policy=do_not_download` の source は download 禁止。`beauty_account` は対象外。

## 関連 doc

- [video-reference-pipeline.md](video-reference-pipeline.md) — 動画参考パイプライン詳細
- [cloudflare-transcription-runbook.md](cloudflare-transcription-runbook.md) — 文字起こし実 API 運用
- [clip-candidate-runbook.md](clip-candidate-runbook.md) — 切り抜き候補生成
- [reference-pipeline-runbook.md](reference-pipeline-runbook.md) — 全 CLI 横断の安全設計
## v2 Reference Expansion (2026-06-30)

New safe entrypoints:

- `scripts/collect_video_references.py`: plans YouTube/TikTok metadata rows without downloading video.
- `scripts/transcribe_video_reference.py`: thin gated transcription entrypoint. Real API requires `ALLOW_TRANSCRIPTION_API=true` and `--allow-real-transcription`.
- `scripts/analyze_video_structure.py`: transcript structure analysis for hooks/topics.
- `scripts/generate_video_reference_posts.py`: creates 3-10 text-only ideas as `WAITING_REVIEW`.
- `scripts/generate_clip_candidates.py`: plans clip candidates only. Third-party defaults to `third_party_reference_only`.

Safety rules:

- Third-party video is reference analysis only.
- Transcript is used only when official/API text is available or the API gate is explicitly opened.
- Download/cut/upload/repost is prohibited for `third_party_reference_only`.
- Generated ideas are `WAITING_REVIEW` or `DRAFT`, never `READY`.

## Public Metadata Adapter (2026-06-30)

`scripts/collect_video_references.py` can fetch public page metadata for YouTube/TikTok reference URLs without downloading video.

```bash
python3 scripts/collect_video_references.py \
  --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
  --fetch-metadata \
  --dry-run
```

Dry-run result on 2026-06-30:

- YouTube title / author / thumbnail metadata was fetched from public metadata.
- `download=false`, `can_download=false`, `can_cut=false`, `can_upload=false`.
- `rights_status=third_party_reference_only`.
- Transcript remains gated: use official/API transcript only. Real transcription API requires `ALLOW_TRANSCRIPTION_API=true` plus explicit confirmation.

TikTok/YouTube third-party videos remain reference-analysis only. Do not download, cut, upload, or repost unless the asset is owned/licensed and the separate media gates are opened.

## Dependency Adapters

- `yt-dlp`: `collect_video_references.py --metadata-adapter yt-dlp` に接続済み。`download=False` / `skip_download=True` でmetadataのみ。
- `youtube-transcript-api`: `collect_video_references.py --fetch-transcript` と `transcribe_video_reference.py --fetch-youtube-transcript` に接続済み。公式/公開字幕が無い場合は `UNAVAILABLE`。
- `google-api-python-client`: optional。YouTube Data APIキー/Quotaが必要なため未導入。
- `TikTokApi`, `pytube`, `moviepy`, `whisper`, `faster-whisper`, `PaddleOCR`, `VoxCPM`: optional。重さ、規約、安定性、認証、環境依存があるため未導入。

## 2026-07-01 Adapter Verification

- `yt-dlp` adapter fetched YouTube metadata in dry-run with `download=false`.
- `youtube-transcript-api` adapter fetched transcript metadata/count in dry-run with `download=false`; transcript text preview is suppressed.
- TikTok profile URL dry-run returns `UNAVAILABLE` quickly with `tiktok_profile_metadata_not_supported_no_download`; use an individual `/video/` URL for metadata checks.
- No video download, cut, upload, repost, or external transcription API call was executed.

## Rights State Update (2026-07-01)

`collect_video_references.py` now accepts `--rights-status`.

- Default is `third_party_reference_only`, so YouTube/TikTok references stay analysis-only with `can_download=false`, `can_cut=false`, and `can_upload=false`.
- `owned`, `licensed`, or `approved_creator_clip` can be marked as media-pipeline eligible, but this still does not download video. It only marks the row for a later explicitly confirmed media workflow.
- Individual TikTok `/video/` URLs can be checked for metadata in dry-run. Profiles/playlists are not expanded for download.

Do not cut or repost YouTube/TikTok third-party clips. Use structure, hook, topic, and transcript analysis only.

## Source Registry Inventory Update (2026-07-01)

- YouTube channel/account references are registered for `night_scout`, `liver_manager`, and `beauty_account`.
- TikTok references are registered only for `beauty_account`; `night_scout` and `liver_manager` TikTok video references are TODO placeholders until a human provides real `/video/` URLs.
- Individual YouTube clip target video URLs are not selected yet; `youtube_night_scout_reference_todo` and `youtube_liver_reference_todo` are placeholders with empty `source_url`.
- All video TODO placeholders are `fetch_enabled=false`, `manual_only=true`, `rights_status=unknown`, `clip_enabled=false`, and `media_pipeline_eligible=false`.
- Full inventory: `docs/source-registry-inventory.md`.

## Library Policy (2026-07-02)

- YouTube metadata: use `yt-dlp` with `download=false`.
- YouTube transcript: use `youtube-transcript-api` when public/official captions exist; transcript preview/body is not printed.
- TikTok metadata: prefer individual `/video/` URLs through `yt-dlp`; `tiktok-to-ytdlp` remains optional helper, not production-enabled.
- TikTok profile URLs are stored as references/placeholders and are not expanded into downloadable media.
- Agent Reach and last30days-skill are optional research/source-discovery signals only.

## Autonomous Loop Connection (2026-07-02)

Video references are now connected to `scripts/run_autonomous_loop.py` for the approved pilot path.

- YouTube reference rows can produce text-only Threads idea candidates from structure/hook analysis.
- Current autonomous pilot YouTube source `src_lm_yt_cand_001` is a channel URL (`https://www.youtube.com/@suu-san_pococha`), so transcript fetch can be `UNAVAILABLE` because channel URLs do not provide a single `video_id`.
- To improve transcript/structure quality, provide an individual YouTube video URL for the relevant account/source.
- Transcript fetch is attempted only through the existing safe transcript adapter. If a channel URL has no video ID, the result is `UNAVAILABLE` and the loop falls back to metadata/structure only.
- TikTok analysis is wired but requires a real individual `/video/` URL. Current `night_scout` and `liver_manager` TikTok rows remain TODO placeholders and are skipped.
- The autonomous output suppresses transcript body/preview.
- `download=false`, `cut=false`, `upload=false`, `repost=false` are invariant for third-party video references.

This connection does not make any media pipeline row eligible. Media eligibility still requires `owned`, `licensed`, or `approved_creator_clip` plus permission evidence and separate confirm gates.

## 2026-07-04 TikTok/YouTube Reference Status

Current supported scope:

- YouTube/TikTok reference analysis for text-only Threads idea generation.
- YouTube metadata where available.
- YouTube transcript path exists, but channel URLs may return `UNAVAILABLE`; individual video URLs are required for reliable transcript work.
- TikTok individual `/video/` URL metadata path exists.
- Analysis can seed text-only Threads posts after `final_public_post_validator`.

Not enabled in production:

- third-party video download
- third-party video cut
- third-party video upload
- third-party video repost
- video + text Threads posting
- TikTok account URL auto expansion
- TikTok account URL auto clip extraction

New `liver_manager` YouTube/TikTok URLs are approved creator references for Media Growth Engine planning. They must stay `fetch_enabled=false` and `manual_only=true`; their account/channel URLs are not auto-expanded or treated as direct download targets. Real download/cut/upload/video post requires an individual video URL, `approved_creator_clip` permission evidence, and the explicit env plus CLI confirmation gates.

## Media Growth Engine Status (2026-07-04)

Implemented but not scheduled for automatic media posting:

- `scripts/run_media_growth_engine.py`: selects permitted `liver_manager` sources, checks rights/permission evidence, plans transcript/metadata analysis, creates clip candidate rows, creates a reader-facing `public_post_text`, and runs `final_public_post_validator`.
- `scripts/download_approved_media.py`: dry-run by default; real download requires an individual video URL, `ALLOW_VIDEO_DOWNLOAD=true`, `--download`, and `--confirm-download`.
- `scripts/cut_approved_clips.py`: dry-run by default; real cut requires `owned`, `licensed`, or `approved_creator_clip`, `ALLOW_VIDEO_CUT=true`, `--cut`, and `--confirm-cut`.
- `scripts/upload_media_assets.py`: dry-run by default; Cloudinary upload requires approved rights, `ALLOW_CLOUDINARY_UPLOAD=true`, `--upload`, and `--confirm-upload`.
- `scripts/media_post_validator.py`: validates approved rights, permission status, video duration/aspect, account/platform, media URL/asset ID, and public post text before any video + text Threads post.

Still not enabled in scheduled production:

- Third-party or unknown-rights media download/cut/upload/repost.
- Channel/account URL unlimited download.
- TikTok account URL automatic expansion.
- Cloudinary real upload.
- Scheduled video + text Threads posting.
- Transcription API real calls.

Media PDCA is record/proposal only. Learning rules and prompt changes remain review-gated and must not auto-apply.

## Source Video Discovery (2026-07-05)

Media Growth Engine no longer depends only on manually entering an individual video URL first. Approved YouTube/TikTok channel/account sources can produce bounded `source_videos` candidates:

- Discovery is limited to sources with `rights_status` in `owned`, `licensed`, or `approved_creator_clip` and `permission_status=approved`.
- `third_party_reference_only`, `reference_only`, `unknown`, `restricted`, and `not_allowed` remain blocked from media pipeline discovery.
- `max_videos_per_source_scan=50`, `max_new_videos_per_source_per_run=10`, and `max_total_new_videos_per_run=20` are enforced.
- TikTok account discovery is limited/manual-safe and must not become unbounded profile scraping.
- Dedupe uses `platform + source_id + video_id`, then canonical video URL, then content hash/title-duration fallback.
- Already seen, clipped, or posted videos are treated as duplicates for discovery.
- `source_videos` records carry `DISCOVERED -> TRANSCRIPT_PLANNED -> ANALYZED -> CLIP_CANDIDATES_READY -> DOWNLOADED -> CUT -> UPLOADED -> POSTED/SKIPPED/BLOCKED`.

Clip candidate generation is now video-based:

- One video can create 1-3 clip candidates.
- Videos under 25 seconds generate 1 clip.
- Videos from 25-90 seconds generate up to 2 clips.
- Videos over 90 seconds generate up to 3 clips.
- Overlapping ranges within the configured tolerance are blocked/merged by duplicate policy.
- Each clip candidate carries `source_video_id`, `video_id`, `canonical_video_url`, `duplicate_clip_key`, `public_post_text`, and `public_post_validator_status`.

Real download/cut/upload/video post is still not scheduled. It remains env plus confirm gated and starts from reviewed `source_video_id` / `clip_candidate_id`.

## Text-Only Schedule Boundary After 2026-07-07 Recovery

The autonomous text-only schedule was repaired without enabling media execution:

- `run_autonomous_loop.py` may use video/reference analysis as text inspiration only.
- If video/source analysis fails, the runner can continue to safe text fallback generation.
- Media Growth Engine execution remains gated for real media operations.
- `source_video_discovery_apply_enabled=true` is now used by the scheduled aftercare workflow to save approved-source `source_videos` only.
- Clip candidate generation can be saved to `video_clip_candidates` for approved sources.
- `download_enabled=false`, `cut_enabled=false`, `upload_enabled=false`, `video_post_enabled=false` remain the default.
- No scheduled workflow posts video or media.

Next media production step, when explicitly requested, should start from reviewed `source_video_id` / `clip_candidate_id`. It must not jump directly to download/cut/upload/post without env gates, confirm flags, rights evidence, and `media_post_validator.py`.

## Production Autopilot Media Aftercare (2026-07-10)

The production aftercare workflow is allowed to run the safe media planning layer automatically:

- discover approved `liver_manager` YouTube/TikTok source videos
- dedupe by video id and canonical URL
- write `source_videos` rows when Sheets credentials are present
- generate up to three non-overlapping clip candidates per video
- write `video_clip_candidates` rows with `public_post_text` preview and validator status

It is not allowed to download, cut, upload, or post media. `third_party_reference_only`, `reference_only`, and `unknown` sources remain analysis-only and are not eligible for media pipeline records beyond safe reference planning.

## Approved Media Preparation And Posting (2026-07-13)

For the 13 user-approved liver_manager/night_scout sources,
`source_role=approved_media`, `rights_status=approved_creator_clip`, and
permission evidence are required together. The pipeline is deliberately split:

1. Advance preparation performs bounded discovery, local transcript, topic
   transformation, 9:16 cut, and Cloudinary upload. It ends in `MEDIA_READY`
   and never posts.
2. The account media slot can use only an uploaded, unused `MEDIA_READY` asset.
   It never performs download, cut, upload, or transcription in the posting
   window.

No subtitles are burned into posted video: `subtitle_enabled=false` and the
cut runner receives `burn_subtitles=false`. Video text is still mandatory and
must pass `final_public_post_validator`; only `public_post_text` is passed to
the Threads publisher.

Night Scout uses an explainable subject gate. Male-scout talking-head,
store-PR/recruiting cues, or missing female-subject evidence are analysis-only
until an explicit subject review exists. Channel-level permission never proves
that every individual video is appropriate.

## Direct Reference Media

`source_posts` and `source_post_media` preserve the original post-to-asset
link. `run_direct_reference_media_pipeline.py` requires explicit
`direct_media_reuse` mode plus download/store/repost/new-caption permission
scope; `approved_creator_clip` alone is insufficient. The public caption is a
new `public_post_text`, never the source post body. Current Threads transport
is video-only; a multi-image/carousel candidate is blocked with an explicit
reason until carousel publishing is implemented, never reduced silently.
