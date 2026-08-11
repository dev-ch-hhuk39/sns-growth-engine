# Source Fetcher Installation Guide

Phase 13 で使用するフェッチャー依存ツールの導入手順。

## ツール一覧と必要性

| ツール | 対象アダプター | 必須 / 任意 |
|---|---|---|
| `yt-dlp` | `yt_dlp`, `tiktok_to_ytdlp` | 動画収集に必須 |
| `ffmpeg` | `yt_dlp` (切り抜き時) | 動画 cut に必須 |
| `youtube-transcript-api` | `youtube_transcript` | 字幕取得に必須 |
| Agent Reach | `agent_reach` | Web/Jina参照補助に任意 |
| Python 3.10+ | 全て | 必須 |

## 導入手順

### yt-dlp

```bash
pip install yt-dlp
# または
brew install yt-dlp
```

バージョン確認:
```bash
yt-dlp --version
```

### ffmpeg

```bash
brew install ffmpeg   # macOS
# または apt install ffmpeg (Ubuntu)
```

バージョン確認:
```bash
ffmpeg -version
```

### youtube-transcript-api

```bash
pip install youtube-transcript-api
```

確認:
```bash
python3 -c "import youtube_transcript_api; print('OK')"
```

## ToolDoctor で一括確認

```bash
python3 scripts/check_source_fetcher_tools.py
```

出力例:
```
=== Source Fetcher Tool Doctor ===
  ✓ [OK] yt-dlp (2025.01.01)
  ✗ [NOT_INSTALLED] ffmpeg  → yt_dlp
  ✓ [OK] youtube-transcript-api (0.6.2)
  ✓ [OK] python (3.11.0)

  3 OK / 1 NOT_INSTALLED / 4 total

  [WARN] 一部のツールが未導入です。上記のインストール手順を参照してください。
  ※ NOT_INSTALLED は WARN（FAIL ではない）。未導入のアダプターは BLOCKED になります。
```

**重要**: `NOT_INSTALLED` はエラーではなく警告。そのアダプターが実行時に `NOT_INSTALLED` を返すだけで、他のアダプターは正常に動作します。

## TikTok Cookie について

`tiktok_to_ytdlp` アダプターはブラウザ Cookie が必要です:

```bash
yt-dlp --cookies-from-browser chrome "https://www.tiktok.com/@HANDLE/video/VIDEO_ID"
```

Cookie なしでは多くの動画が取得できません。TikTok Cookie の管理には十分注意してください（Cookie 流出による不正アクセスリスク）。

## agent_reach アダプターについて

2026-08-11に公式GitHubのcommit `1221ecd0c3e0502ee37406f03543bedf7503f2c7`
を `~/.agent-reach-venv` へ隔離installし、Agent Reach 1.5.0を実測した。repo adapterは
generic Web/Jinaのread-only参照補助だけに限定する。Agent ReachにThreads/TikTokのnative
channelはなく、プロファイルから個別投稿やメディアを発見できるとは扱わない。

X native channelは明示的なログイン/cookie設定が必要。cookieの自動抽出やbrowser経由の
acquisitionは有効化しない。X physical mediaとYouTube physical mediaの正本は引き続き
`yt-dlp`で、Threads/TikTok physical mediaはdeferredとする。

## 参考

- `docs/yt-dlp-fetcher.md` — yt-dlp アダプター詳細
- `docs/tiktok-to-ytdlp-fetcher.md` — TikTok アダプター詳細
- `docs/agent-reach-fetcher.md` — agent_reach アダプター詳細
- `docs/youtube-transcript-fetcher.md` — 字幕アダプター詳細
