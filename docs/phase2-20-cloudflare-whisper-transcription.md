# Phase 2.20 — Cloudflare Whisper 文字起こし基盤

**実装日**: 2026-05-31  
**ステータス**: 完了

---

## 概要

動画の文字起こしに Cloudflare Workers AI の Whisper モデルを使用する。  
**課金回避を最優先**とし、実API呼び出しは明示的に許可しない限り行わない。

---

## 安全ガード（2重）

| ガード | 場所 | 説明 |
|---|---|---|
| 環境変数ガード | `.env` | `ALLOW_TRANSCRIPTION_API=false`（デフォルト）。true にするまで実APIは呼ばれない |
| コードガード | `CloudflareWhisperClient.__init__` | `allow_transcription_api=True` を渡さなければ常に dry_run モードで動作 |

---

## モジュール構成

```
src/transcription/
  __init__.py
  cloudflare_whisper_client.py   Cloudflare API クライアント
  transcription_limiter.py       日次120分上限管理
  transcript_parser.py           文字起こし結果の解析・クリップ候補抽出

scripts/
  transcribe_videos.py           実行CLI
```

---

## CloudflareWhisperClient

| メソッド | 説明 |
|---|---|
| `from_config(transcription_cfg, dry_run)` | `get_transcription_config()` から生成 |
| `transcribe(audio_path, ...)` | 文字起こし実行。dry_run=True または ALLOW_TRANSCRIPTION_API=false の場合はモック |

TranscriptionResult:
```python
@dataclass
class TranscriptionResult:
    transcript_id: str
    reference_post_id: str
    status: str          # done / failed / skipped_limit
    transcript_text: str
    segments: list[dict] # word-level タイムスタンプ
    duration_seconds: float
    processed_minutes: float
    error: str
```

---

## TranscriptionLimiter

日次120分の上限を管理する。

**設計**:
- 起動時に `transcription_runs` タブから当日の使用量を1回読み込む
- 実行中はインメモリで累積（per-call Sheets 読み取りなし → レートリミット回避）
- `flush()` で終了時に1回だけ Sheets に書き戻す

**使用方法**:
```python
limiter = TranscriptionLimiter(client, limit_minutes=120)
if limiter.can_process(duration_seconds=480.0):
    result = whisper.transcribe(...)
    limiter.record(duration_seconds=480.0, status=result.status)
else:
    limiter.record_skip()
limiter.flush()  # 終了時に1回
```

---

## transcript_parser.py

ルールベースで文字起こし結果を解析（LLM不使用）。

| 関数 | 説明 |
|---|---|
| `parse_segments(segments_json_or_list)` | JSON文字列またはlistを list[dict] に変換 |
| `extract_clip_window(segments)` | word-levelタイムスタンプから最適なクリップ区間を返す |
| `extract_hook_sentence(transcript_text)` | 冒頭フック文を抽出（最初の句読点まで） |
| `build_clip_candidate(transcript, account_id)` | transcript dict から clip_candidates 行を生成 |
| `build_clip_candidates_from_transcripts(transcripts, account_id)` | バッチ処理 |

---

## 日次フロー

```
1. transcribe_videos.py 起動
2. TranscriptionLimiter 初期化（当日の使用量を Sheets から1回読み込み）
3. reference_posts から content_type=video, transcription_status=pending を取得
4. 各動画:
     a. limiter.can_process() で上限チェック → 超過はスキップ
     b. whisper.transcribe() → TranscriptionResult
     c. limiter.record(duration_seconds, status)
     d. video_transcripts に保存
5. limiter.flush() → transcription_runs に1行保存
```

---

## 費用コントロール

- Cloudflare Workers AI Whisper: 無料枠 = 1日10,000 neuron（≒ 約100分の音声）
- `DAILY_TRANSCRIPTION_MINUTES_LIMIT=120` が安全上限（デフォルト）
- 失敗・上限超過時は次回再実行（fallback なし）
- 詳細: `docs/transcription-cost-control.md`
