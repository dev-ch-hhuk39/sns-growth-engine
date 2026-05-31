# 文字起こしコスト制御ポリシー

**作成日**: 2026-05-31

---

## Cloudflare Workers AI Whisper 無料枠

| 項目 | 仕様 |
|---|---|
| モデル | `@cf/openai/whisper` |
| 無料枠 | 1日 10,000 neurons（≒ 約80〜100分の音声） |
| 超過時 | Billable に移行（Workers Paid プランが必要） |

---

## 日次上限設定

```env
DAILY_TRANSCRIPTION_MINUTES_LIMIT=120
```

- デフォルト: **120分/日**（無料枠の想定最大値に余裕を持たせた値）
- 変更する場合は `.env` で上書き可能

---

## 超過時の挙動

- `TranscriptionLimiter.can_process()` で上限チェック → 超過は **スキップ**
- スキップした動画は `transcription_status=pending` のまま残る → **次回再実行**
- fallback（別プロバイダーへの自動切り替え）は**しない**
- 失敗（API エラー）も同様: `status=failed` のまま残し、次回再実行

---

## 安全ガード

```
ALLOW_TRANSCRIPTION_API=false   # デフォルト: 実API呼び出し禁止
```

- `false` の間は `CloudflareWhisperClient` が常に mock レスポンスを返す
- `true` にするには `.env` を明示的に変更 + `--allow-real-transcription` フラグ（両方必要）

---

## 費用試算

| 動画長 | 処理時間(分) | 1日処理可能本数(120分上限) |
|---|---|---|
| 3分（TikTok） | 3分 | 40本 |
| 8分（YouTube短め） | 8分 | 15本 |
| 15分（YouTube中） | 15分 | 8本 |
| 30分（YouTube長め） | 30分 | 4本 |

---

## モニタリング

`transcription_runs` タブで日次使用量を確認できる。

| 列 | 確認内容 |
|---|---|
| used_minutes | 今日の消費分数 |
| remaining_minutes | 残り上限分数 |
| processed_count | 成功本数 |
| skipped_daily_limit_count | 上限超過スキップ数 |
| failed_count | API失敗数 |
