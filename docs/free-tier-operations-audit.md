# 外部サービス無料枠・コスト監査

## 概要

- 作成日: 2026-06-20
- 目的: sns-growth-engine v2 が利用する外部サービスの無料枠・課金条件・超過リスクを把握する

> **注意:** 各サービスの無料枠は予告なく変更される。定期的にこのドキュメントを最新版に更新すること。

---

## サービス別監査

### 1. X (Twitter) API

| 項目 | 内容 |
|---|---|
| 利用 Tier | Free（または Basic） |
| Free Tier 制限 | 月1,500 POST write（Free）/ 月50,000 POST write（Basic $100/月） |
| 読み取り制限 | Free: 1ユーザーあたり1ヶ月 1,500件 GET / Basic: 10,000件 |
| 投稿上限の考慮 | 1日6回 × 30日 = 180回/月（Free 枠: 1,500 の 12%） |
| 超過リスク | Free Tier で月180件は余裕あり。API Tier を Twitter Dev Portal で確認推奨 |
| 課金トリガー | 月1,500 POST を超えると 429 Too Many Requests |
| 対策 | `scripts/check_credentials_readiness.py` で API Key 設定確認。投稿頻度は config で管理 |
| 確認場所 | https://developer.twitter.com/en/portal/dashboard |

### 2. Threads API (Meta)

| 項目 | 内容 |
|---|---|
| 無料枠 | 制限なし（2026年現在、投稿数上限なし） |
| トークン期限 | 長期トークン: 60日（要リフレッシュ） |
| Rate Limit | 250 API calls / hour（投稿は別カウント） |
| 超過リスク | トークン失効による投稿停止リスクが最大（60日ルール） |
| 対策 | 45日ごとに `scripts/refresh_threads_token.py` を実行 |
| token 管理 | `data/threads_tokens/{account_id}.json` にローカル保存 |
| 確認場所 | https://developers.facebook.com/apps/ |

### 3. Google Sheets API

| 項目 | 内容 |
|---|---|
| 無料枠 | 300 requests / minute per project（Service Account 経由） |
| ストレージ制限 | Drive 15GB（無料）/ シートデータは軽量 |
| 超過リスク | 大量バッチ書き込みで 429 が出る可能性 |
| 対策 | `sheets_client.py` 内に `time.sleep(0.5)` を挿入（現在実装済み） |
| 現状 | 1日2〜8回の投稿管理では枠内。問題なし |
| 確認場所 | https://console.cloud.google.com/apis/api/sheets.googleapis.com |

### 4. Gemini API (Google)

| 項目 | 内容 |
|---|---|
| 無料枠（Free Tier） | gemini-1.5-flash: 15 req/min, 1,500 req/day, 1M tokens/min |
| 無料枠（Gemini 2.0 flash） | 10 req/min, 1,500 req/day |
| 課金起点 | pay-as-you-go 有効化後。無料枠は Cloud Billing なしで利用可 |
| 超過リスク | 1日1,500 req は余裕あり（1投稿 = 1〜2 API call 程度） |
| 推奨モデル | `GEMINI_MODEL_CANDIDATES` に複数モデルを設定してフォールバック対応 |
| 確認場所 | https://aistudio.google.com/ |

### 5. Cloudinary

| 項目 | 内容 |
|---|---|
| 無料枠 | 25 credits/月（1 credit ≈ 1 transformation または 1 upload） |
| ストレージ | 25GB |
| 帯域 | 25GB/月 |
| 超過リスク | 本番投稿に画像を使う場合は消費が増加。現状 `ALLOW_CLOUDINARY_UPLOAD=false` で保護 |
| 現状 | 無効化中（`ALLOW_CLOUDINARY_UPLOAD=false`） |
| 有効化条件 | ユーザー承認後、`.env` に `ALLOW_CLOUDINARY_UPLOAD=true` を一時設定 |
| 確認場所 | https://console.cloudinary.com/ |

### 6. Cloudflare Workers AI（文字起こし）

| 項目 | 内容 |
|---|---|
| 無料枠 | Workers AI: 10,000 neurons/day（Free） |
| Whisper 換算 | 1分の音声 ≈ 約890 neurons（機種依存） |
| 無料換算上限 | 約 11〜12分/day（10,000 ÷ 890） |
| 内部制限 | `DAILY_TRANSCRIPTION_MINUTES_LIMIT=120`（120分/日） |
| 乖離 | 内部制限(120分) > 無料枠実際値(約12分): **要注意** |
| 対策 | Cloudflare Dashboard でニューロン消費量を監視。使用頻度が上がったら有料プランへ移行 |
| 現状 | 無効化中（`ALLOW_TRANSCRIPTION_API=false`） |
| 有効化条件 | ユーザー承認後、`.env` に `ALLOW_TRANSCRIPTION_API=true` を一時設定 |
| 確認場所 | https://dash.cloudflare.com/ → Workers & Pages → AI |

> **DAILY_TRANSCRIPTION_MINUTES_LIMIT 見直し推奨:** Cloudflare Workers AI 無料枠は実際には約12分/日程度。現状の `120` は無料枠の10倍。有効化時は `DAILY_TRANSCRIPTION_MINUTES_LIMIT=10` に変更すること。

### 7. yt-dlp（ローカルツール）

| 項目 | 内容 |
|---|---|
| コスト | 無料（OSS） |
| 利用形態 | ローカル実行 / CLI |
| リスク | YouTube / TikTok の利用規約上の制限。`--confirm-download` なしの実行は禁止 |
| 現状 | `media_policy=do_not_download` 設定の source は download 禁止 |
| 帯域コスト | ローカル帯域のみ（クラウドコストなし） |

### 8. youtube-transcript-api（Python ライブラリ）

| 項目 | 内容 |
|---|---|
| コスト | 無料（OSS） |
| リスク | YouTube が API を変更すると動作停止の可能性 |
| 現状 | テキストのみ取得。動画 download なし |
| 制限 | YouTube が字幕を提供していない動画は取得不可 |

### 9. GitHub Actions

| 項目 | 内容 |
|---|---|
| 無料枠（Public repo） | 無制限 |
| 無料枠（Private repo） | 2,000 分/月 |
| 現状 | 旧 repo: 全 20 ワークフロー停止済み（2026-06-20）|
| 新 repo | GitHub Actions は現時点では不使用（ローカル実行のみ） |
| 超過リスク | 旧 repo 停止後は消費ゼロ |

### 10. ローカル cron / scheduler

| 項目 | 内容 |
|---|---|
| コスト | 無料（ローカル実行） |
| 現状 | 現時点では実装なし（手動 CLI 実行のみ） |
| 将来方針 | cron / launchd（macOS）を使ってスケジューラを設定予定 |
| リスク | ローカルマシン停止時は投稿が止まる |

---

## コスト超過リスクサマリー

| サービス | リスクレベル | 現状 | 優先対策 |
|---|---|---|---|
| Threads トークン失効 | **高** | 60日期限あり | 45日ごとにリフレッシュ |
| Cloudflare Workers AI 超過 | **中** | 無効化中 | 有効化時に上限を 10分/日 に変更 |
| X API Rate Limit | **低** | 月180件（Free 枠 1,500） | API Tier 確認 |
| Gemini API 超過 | **低** | 1日 1,500 req 余裕 | モデルフォールバック設定 |
| Cloudinary 超過 | **低** | 無効化中 | 使用量モニタリング |
| Google Sheets API | **低** | 300 req/min 余裕 | バッチ書き込み時に sleep 済み |
| GitHub Actions | **なし** | 旧 repo 全停止済み | — |

---

## 監視・確認スケジュール

| 頻度 | アクション |
|---|---|
| **45日ごと** | Threads トークンリフレッシュ（`scripts/refresh_threads_token.py`） |
| **月1回** | X API 利用量確認（Twitter Developer Portal） |
| **月1回** | Gemini API 利用量確認（Google AI Studio） |
| **有効化時のみ** | Cloudflare ニューロン消費量確認 |
| **四半期** | 各サービスの無料枠変更を確認し、このドキュメントを更新 |

---

## 関連ドキュメント

- `docs/credential-migration-plan.md`: 認証情報管理
- `docs/cloudflare-transcription-runbook.md`: Cloudflare 文字起こし詳細
- `docs/cloudinary-upload-runbook.md`: Cloudinary 詳細
- `docs/transcription-cost-control.md`: 文字起こしコスト制御
