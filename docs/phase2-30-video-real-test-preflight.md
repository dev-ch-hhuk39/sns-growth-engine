# Phase 2.30: 実動画テスト前提条件チェック（preflight）

## 概要

`scripts/preflight_video_real_test.py` は、実ダウンロード・音声抽出・文字起こしを
実行する前に必要な環境条件が揃っているかを確認するチェックスクリプト。

**このスクリプト自体は実ダウンロード・実API呼び出しを一切行わない。**

---

## チェック項目

| チェック | 成功条件 | レベル |
|---------|---------|--------|
| Python バージョン | 3.9 以上 | INFO / WARN |
| yt-dlp | インストール済み | FAIL（未インストール） |
| ffmpeg | インストール済み | FAIL（未インストール） |
| CLOUDFLARE_ACCOUNT_ID | 環境変数が存在する | WARN（未設定） |
| CLOUDFLARE_API_TOKEN | 環境変数が存在する | WARN（未設定） |
| ALLOW_TRANSCRIPTION_API | `false`（ガード有効） | WARN（true の場合） |
| ALLOW_CLOUDINARY_UPLOAD | `false`（ガード有効） | WARN（true の場合） |
| PUBLISH_ENABLED | `false`（ガード有効） | WARN（true の場合） |
| downloads/ 書き込み権限 | 書き込み可能 | FAIL |
| exports/hermes/ 書き込み権限 | 書き込み可能 | FAIL |

---

## 使い方

```bash
# 通常チェック（WARN は無視、FAIL のみ非ゼロ終了）
python scripts/preflight_video_real_test.py

# 厳格モード（WARN でも非ゼロ終了）
python scripts/preflight_video_real_test.py --strict
```

---

## 実行例

```
============================================================
  preflight_video_real_test.py - 実動画テスト前提条件チェック
============================================================
[INFO] このスクリプトは実ダウンロード・実API呼び出しを一切行いません

  [INFO] Python: 3.11.5
  [PASS] Python version: 3.9+

  [PASS] yt-dlp: found: /usr/local/bin/yt-dlp (version: 2024.12.01)
  [PASS] ffmpeg: found: /usr/local/bin/ffmpeg (ffmpeg version 7.1 ...)

  [WARN] env: CLOUDFLARE_ACCOUNT_ID: 未設定（文字起こし実行に必要）
  [PASS] env: ALLOW_TRANSCRIPTION_API: false（実行ガード有効）
  [PASS] env: PUBLISH_ENABLED: false（実行ガード有効）

  [PASS] downloads/ 書き込み権限: /path/to/v2/downloads
  [PASS] exports/hermes/ 書き込み権限: /path/to/v2/exports/hermes

============================================================
  [PASS]: 8  [WARN]: 1  [FAIL]: 0
============================================================

[RESULT] WARN: 一部項目を確認してください（実行は可能）。
```

---

## FAIL した場合の対処

### yt-dlp が見つからない

```bash
pip install yt-dlp
# または
brew install yt-dlp
```

### ffmpeg が見つからない

```bash
brew install ffmpeg
```

### downloads/ 書き込み不可

```bash
chmod 755 downloads/
```
