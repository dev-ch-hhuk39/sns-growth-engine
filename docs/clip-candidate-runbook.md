# Clip Candidate Runbook

Date: 2026-06-28

文字起こし済み動画から「切り抜き候補」を生成するための標準 CLI 入口。
候補化のみで、ffmpeg による実切り抜き（`--cut`）は本 CLI では BLOCKED。本 doc は薄い入口。

## 標準 CLI

| CLI | 役割 | 既定 |
|---|---|---|
| `generate_clip_candidates.py` | 切り抜き候補生成 | PLAN_ONLY |

## 使い方

```bash
python3 scripts/generate_clip_candidates.py --account-id liver_manager --limit 5 --n-candidates 6
# 本番候補書き込み
python3 scripts/generate_clip_candidates.py --account-id liver_manager --apply --confirm-generate
```

- 主要フラグ: `--account-id` / `--limit`（既定 5） / `--n-candidates`（既定 6） / `--transcript-status`（既定 done） / `--apply` / `--confirm-generate`。
- `--cut`（ffmpeg 実切り抜き）は本 CLI では BLOCKED。実切り抜きはしない。
- 入力: `video_transcripts`（status=done）。出力: `video_clip_candidates`。

## 候補から投稿案へ

切り抜き候補を Threads 投稿案にするには `generate_threads_ideas_from_references.py --source clips` を使う。
[threads-idea-generation-runbook.md](threads-idea-generation-runbook.md) を参照。

## 安全方針

- 候補化（開始秒/終了秒/見出し案/suggested_script 等の artifact）まで。実 download / cut / upload はしない。
- `reuse_policy=no_reuse` / `media_policy=do_not_download` の source は候補化のみで media 利用不可。
- `beauty_account` は対象外。

## 関連 doc

- [video-clip-generation-usage.md](video-clip-generation-usage.md) — 切り抜き生成の詳細
- [youtube-tiktok-clipping-runbook.md](youtube-tiktok-clipping-runbook.md) — 切り抜き運用（実行は承認後）
- [video-reference-runbook.md](video-reference-runbook.md) — 前段（準備・文字起こし）
- [reference-pipeline-runbook.md](reference-pipeline-runbook.md) — 全 CLI 横断の安全設計
