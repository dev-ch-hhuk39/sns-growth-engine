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
