# Source Fetcher ツール選定ガイド（Phase 9）

## 方針

本プロジェクトでは X / Threads / TikTok / YouTube の公式 API を使わない。

理由:
- API コスト・レートリミット・認証複雑性
- アカウント停止リスク
- 開発速度優先

## プラットフォーム別推奨ツール

| プラットフォーム | 推奨ツール | collection_method | 備考 |
|---|---|---|---|
| YouTube | yt-dlp | yt_dlp | メタデータのみ。download 禁止 |
| YouTube Shorts | yt-dlp | yt_dlp | 同上 |
| YouTube 文字起こし | youtube-transcript-api | youtube_transcript | download 不要 |
| TikTok | tiktok-to-ytdlp + yt-dlp | tiktok_to_ytdlp | URL 取得後 yt-dlp |
| X（Twitter） | Agent-Reach CLI | agent_reach | 非公式。要ローカルログイン |
| Threads | ブラウザエクスポート | browser_export | JSON/CSV 手動投入 |
| トレンド分析 | last30days-skill | last30days_skill | 個別投稿ではなくトレンド |
| 手動投入 | JSON / CSV / URL | manual_json / manual_csv / manual_url | 最安全ルート |

## ツールインストール確認

```bash
# yt-dlp
yt-dlp --version

# tiktok-to-ytdlp
tiktok-to-ytdlp --help

# agent-reach
agent-reach --version || npx agent-reach --version

# youtube-transcript-api
python3 -c "from youtube_transcript_api import YouTubeTranscriptApi; print('OK')"

# last30days-skill
last30days --help || npx last30days-skill --help
```

## 制限事項

- すべての実 fetch は `--confirm-fetch` が必要
- ダウンロード（動画バイナリ）は `--confirm-download` が必要（現状 plan_only のみ）
- scraping / 規約違反取得は禁止
- `scrape_disallowed` は常に BLOCKED

## フォールバック戦略

1. ツール未インストール → `NOT_INSTALLED`（テストは mock で通過）
2. 実 fetch できない環境 → `manual_json` で手動投入
3. ブロック済みソース → BLOCKED（priority=99 で管理）
