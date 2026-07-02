# Video Reference Runbook

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
- Transcript fetch is attempted only through the existing safe transcript adapter. If a channel URL has no video ID, the result is `UNAVAILABLE` and the loop falls back to metadata/structure only.
- TikTok analysis is wired but requires a real individual `/video/` URL. Current `night_scout` and `liver_manager` TikTok rows remain TODO placeholders and are skipped.
- The autonomous output suppresses transcript body/preview.
- `download=false`, `cut=false`, `upload=false`, `repost=false` are invariant for third-party video references.

This connection does not make any media pipeline row eligible. Media eligibility still requires `owned`, `licensed`, or `approved_creator_clip` plus permission evidence and separate confirm gates.
