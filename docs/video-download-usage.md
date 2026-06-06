# 動画ダウンロード・音声抽出 使用ガイド

**作成日**: 2026-06-06

---

## 概要

`download_video_assets.py` は yt-dlp で動画をダウンロードし、ffmpeg で音声を抽出する。

---

## コマンド一覧

### dry-run（デフォルト）

```bash
python scripts/download_video_assets.py --account-id night_scout
```

### 実Sheets + dry-run確認

```bash
python scripts/download_video_assets.py --account-id night_scout --use-sheets
```

### 実ダウンロード（両フラグ必要）

```bash
python scripts/download_video_assets.py \
  --account-id night_scout \
  --use-sheets \
  --download --confirm-download
```

### ダウンロード + 音声抽出

```bash
python scripts/download_video_assets.py \
  --account-id night_scout \
  --use-sheets \
  --download --confirm-download \
  --extract-audio --confirm-extract
```

---

## 出力先

| データ | パス |
|---|---|
| 動画ファイル | `downloads/videos/<account_id>/<video_id>.mp4` |
| 音声ファイル | `downloads/audio/<account_id>/<video_id>.wav` |

どちらも `.gitignore` で除外済み。

---

## 音声フォーマット

- コーデック: PCM 16bit
- サンプリングレート: 16kHz
- チャンネル: モノラル

Cloudflare Whisper API の推奨フォーマット。

---

## 安全ガード

| ガード | 設定 |
|---|---|
| ダウンロード実行 | `--download --confirm-download` の両フラグ必要 |
| 音声抽出実行 | `--extract-audio --confirm-extract` の両フラグ必要 |
| TikTok（Phase 2.29）| dry-run 時は planning 成功（success=True）、実ダウンロードは未対応 |
| 大量取得禁止 | `--limit` で件数制限（デフォルト: 5件） |
| Sheets 書き込み | `--test-write` が必要 |

---

## 依存ライブラリ

| ライブラリ | 用途 | インストール |
|---|---|---|
| `yt-dlp` | 動画ダウンロード | `pip install yt-dlp` |
| `ffmpeg` | 音声抽出 | `brew install ffmpeg` (macOS) |

ダウンロード/抽出をしない場合は不要。
