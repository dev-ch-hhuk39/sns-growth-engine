# Legacy Repo Migration Audit

## 概要

- 作成日: 2026-06-20
- 担当AI: Claude Code (Sonnet 4.6)
- 目的: 旧3リポジトリの実態調査、移植候補の整理、統合フェーズへの移行準備

今後の運用は `dev-ch-hhuk39/sns-growth-engine` に一本化する。  
旧3リポジトリは **停止 → 一定期間保留 → archive** の順で整理する。

---

## 旧リポジトリ一覧

| リポジトリ名 | 対象アカウント | プラットフォーム | 投稿頻度 | 最終push |
|---|---|---|---|---|
| X_autopost_yoru | night_scout | X (Twitter) | 6回/日 | 2026-06-19 (keepalive) |
| threads_auto_post_gs | night_scout | Threads | 2回/日 | 2026-06-19 (keepalive) |
| threads-liver-coachhing | liver_manager | Threads | 8回/日 | 2026-06-19 (keepalive) |

**合計: 約16回/日が現在も自動投稿中**  
新旧並行稼働は重複投稿リスクがあるため、**旧repo停止が新repo本番投稿の前提条件**。

---

## X_autopost_yoru

### 基本情報

- 用途: X (Twitter) への自動投稿（スカウト夜職アカウント向け）
- 対象アカウント: night_scout
- プラットフォーム: X (Twitter) API v2
- keepalive commit: あり（GitHub Actions が `last_run.txt` に日付を書き込む）

### スケジューラー

| ワークフロー | cron (UTC) | JST 時刻 | 投稿数/日 |
|---|---|---|---|
| x_time_window.yml | 45 4, 45 8 | 13:45, 17:45 | 2回 |
| x_legacy_tab_time_window.yml | 45 3, 45 6, 45 10, 45 14 | 12:45, 15:45, 19:45, 23:45 | 4回 |

- 投稿元シート: `x_time_window.yml` → `03_投稿キュー` タブ  
- 投稿元シート: `x_legacy_tab_time_window.yml` → `x_autopost_yoru` タブ（旧タブ）

### env 名一覧（値は記載しない）

```
X_API_KEY
X_API_SECRET
X_ACCESS_TOKEN
X_ACCESS_TOKEN_SECRET
SHEET_ID
SHEET_TAB
GCP_SA_JSON          # JSONをそのまま文字列で格納（新repoとは形式が異なる）
GEMINI_API_KEY
DISCORD_WEBHOOK_URL
DEDUP_TAB
```

### 移植候補

| スクリプト | 新 repo 対応箇所 | 移植優先度 |
|---|---|---|
| x_collect_posts.py | src/fetchers/ (参考投稿収集) | 低（新repo独自実装済み） |
| x_generate_review_rewrites.py | src/generators/ (投稿生成) | 低（新repo独自実装済み） |
| x_prepare_media_assets.py | src/media_processor/ | 参考のみ |
| x_pipeline_config.json | config/accounts/ 設定の参考 | 参考のみ |
| x_sheet_schema.py | src/sheets_client.py TAB_DEFINITIONS | 不要（新repo独自定義済み） |

### 危険箇所

- `auto_post.py`: SHEET_ID / GCP_SA_JSON を env から直接読み込み、X API v2 本番投稿実行
- `x_legacy_tab_autopost.py`: 廃止予定の旧タブ `x_autopost_yoru` へ投稿継続中
- `GCP_SA_JSON` の形式が JSON文字列（新 repo は base64 または SA ファイルパス方式と異なる可能性あり）
- GitHub Secrets に X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET が保管中

### 停止推奨手順

1. GitHub → `dev-ch-hhuk39/X_autopost_yoru` → Settings → Actions → General
2. `x_time_window.yml` を disable
3. `x_legacy_tab_time_window.yml` を disable
4. 翌日の実行予定時刻を過ぎたことを確認してから次フェーズへ

### archive 推奨可否

- 停止確認後 30日間は保留（投稿が重複していないか監視）
- 問題なければ archive 可

### secret rotate 推奨

- 新 repo 移行完了後: `X_API_KEY` / `X_API_SECRET` / `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET` を rotate 推奨
- rotate 後: 旧 repo の GitHub Secrets は削除可

---

## threads_auto_post_gs

### 基本情報

- 用途: Threads への自動投稿（スカウト夜職アカウント向け）
- 対象アカウント: night_scout
- プラットフォーム: Threads Graph API (`graph.threads.net/v1.0`)
- keepalive commit: あり

### スケジューラー

| ワークフロー | cron (UTC) | JST 時刻 | 投稿数/日 |
|---|---|---|---|
| threads-daily.yml | 45 4, 45 8 | 13:45, 17:45 | 2回 |

投稿元シート: `03_投稿キュー` タブ（`main_gsheet.py --mode batch --max-per-run 1`）

### env 名一覧（値は記載しない）

```
THREADS_ACCESS_TOKEN   # 60日期限の長期トークン
THREADS_USER_ID
SHEET_URL
SHEET_TAB
SA_JSON_BASE64         # base64エンコードされたSAJson（X_autopost_youruとは形式が異なる）
GEMINI_API_KEY
DISCORD_WEBHOOK_URL
DEDUP_TAB
```

### 移植候補

| スクリプト | 新 repo 対応箇所 | 移植優先度 |
|---|---|---|
| main_gsheet.py | scripts/publish_threads_post.py | 参考のみ（新repo独自実装） |
| collect.py | src/fetchers/ | 不要 |
| refresh_token.py | scripts/refresh_threads_token.py | **高（Task G で実装）** |

`refresh_token.py` の実装（Threads Graph API トークンリフレッシュ）はそのまま参考にできる:
- エンドポイント: `https://graph.threads.net/refresh_access_token`
- パラメータ: `grant_type=th_refresh_token`, `access_token=<current_token>`
- 旧 repo は GITHUB_OUTPUT に書き出し → 新 repo はローカル JSON に保存する方式に変更

### 危険箇所

- `main_gsheet.py`: Threads API 本番投稿を直接実行
- `THREADS_ACCESS_TOKEN` が 60日期限。期限切れ前に新 repo 側でリフレッシュが必要
- `SA_JSON_BASE64` と `GCP_SA_JSON`（X_autopost_youru）の形式が異なる点に注意
- night_scout の Threads 投稿が X_autopost_yoru 停止後も継続される可能性

### 停止推奨手順

1. GitHub → `dev-ch-hhuk39/threads_auto_post_gs` → Settings → Actions → General
2. `threads-daily.yml` を disable
3. 翌日 13:45 / 17:45 JST を過ぎたことを確認

### archive 推奨可否

- 停止確認後 30日間保留
- 問題なければ archive 可

### secret rotate 推奨

- 新 repo 移行完了後: `THREADS_ACCESS_TOKEN` / `THREADS_USER_ID` を rotate 推奨
- Threads トークンは一度 refresh すると旧トークンが無効になるため、移行タイミングに注意

---

## threads-liver-coachhing

### 基本情報

- 用途: Threads への自動投稿（ライバーコーチングアカウント向け）
- 対象アカウント: liver_manager
- プラットフォーム: Threads Graph API (`graph.threads.net/v1.0`)
- keepalive commit: あり
- **高頻度投稿: 8回/日。最も影響が大きい。停止最優先。**

### スケジューラー

| cron (UTC) | JST 時刻（±15分） |
|---|---|
| 45 14 * * * | 00:00 前後 |
| 45 17 * * * | 03:00 前後 |
| 45 20 * * * | 06:00 前後 |
| 45 23 * * * | 09:00 前後 |
| 45 2 * * *  | 12:00 前後 |
| 45 5 * * *  | 15:00 前後 |
| 45 8 * * *  | 18:00 前後 |
| 45 11 * * * | 21:00 前後 |

投稿元: `main_gsheet.py`（threads_auto_post_gs と同一アーキテクチャ）

### env 名一覧（値は記載しない）

```
THREADS_ACCESS_TOKEN   # liver_manager 専用。threads_auto_post_gs とは別の値
THREADS_USER_ID        # liver_manager 専用
SHEET_URL
SHEET_TAB
SA_JSON_BASE64
GEMINI_API_KEY
DISCORD_WEBHOOK_URL
DEDUP_TAB
```

### 移植候補

| スクリプト | 新 repo 対応箇所 | 移植優先度 |
|---|---|---|
| main_gsheet.py | scripts/publish_threads_post.py | 参考のみ |
| refresh_token.py | scripts/refresh_threads_token.py | **高（Task G で共通化）** |
| x_collect_bird_posts.py | src/fetchers/ | 不要（新repo独自） |

### 危険箇所

- **最高頻度: 8回/日**。新旧並行稼働は絶対に避けること
- liver_manager の `THREADS_ACCESS_TOKEN` と night_scout のものを混同しないよう注意
- `x_collect_bird_posts.py`, `x_analyze_posts.py` 等の X 収集スクリプトが混在（用途の範囲が広い）
- スクリプト構成が threads_auto_post_gs と酷似しているが、一部差分あり（`queue_gsheet.py` の有無など）

### 停止推奨手順

1. GitHub → `dev-ch-hhuk39/threads-liver-coachhing` → Settings → Actions → General
2. `threads-daily.yml` を disable
3. 翌日の投稿予定時刻を複数回過ぎたことを確認（8回/日のため、24時間後に全スロット確認）

### archive 推奨可否

- 停止確認後 30日間保留
- 問題なければ archive 可

### secret rotate 推奨

- 新 repo 移行完了後: `THREADS_ACCESS_TOKEN` / `THREADS_USER_ID` (liver_manager 用) を rotate 推奨
- night_scout 用トークンとは別で管理

---

## 統合後の運用方針（一本化後）

| 旧repo | 対応するアカウント | 移行先 |
|---|---|---|
| X_autopost_yoru | night_scout / X | sns-growth-engine: `publish_x_post.py` + GitHub Actions |
| threads_auto_post_gs | night_scout / Threads | sns-growth-engine: `publish_threads_post.py` (Phase 3-E) |
| threads-liver-coachhing | liver_manager / Threads | sns-growth-engine: `publish_threads_post.py` (Phase 3-E) |

### 移行可能な最小構成

新 repo で本番投稿を開始するには以下が揃っていること:

- [ ] `publish_x_post.py`: Phase 3-D 以降（実投稿対応済み）
- [ ] `publish_threads_post.py`: Phase 3-E 実装完了
- [ ] `scripts/refresh_threads_token.py`: トークンリフレッシュ実装完了
- [ ] `.env` に認証情報設定済み
- [ ] 旧 repo の全 GitHub Actions を disable 済み

### Spreadsheet 移行方針

- 旧 repo のシート: `SHEET_ID` / `SHEET_URL` で管理（別々）
- 新 repo: `SNS_MASTER_SHEET_ID` 一元管理
- 投稿キュー `03_投稿キュー` の移行は手動（新 repo のスキーマと互換性なし）
- 旧 repo のシートは停止後も読み取り専用で参照可

---

## 調査で確認できなかった事項（確認推奨）

1. 旧 repo の GitHub Secrets 実際の値（値自体は確認不要、存在確認のみ）
2. SHEET_ID / SHEET_URL が指すスプレッドシートの現在の行数（移行対象データ量の見積もり）
3. liver_manager の `THREADS_ACCESS_TOKEN` の残り有効期限（60日ルール）
4. X_API_KEY の API tier（Free / Basic / Pro — 投稿上限に影響）

---

## 関連ドキュメント

- `docs/legacy-repo-shutdown-plan.md`: 停止手順の詳細
- `docs/credential-migration-plan.md`: 認証情報の移行手順
- `docs/production-launch-checklist.md`: 新 repo 本番開始チェックリスト
