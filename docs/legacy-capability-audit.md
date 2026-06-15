# Legacy Capability Audit

## 概要

Phase 1〜8 で実装した機能の現在の状態・活用状況・技術的負債を記録します。

---

## Phase 1〜3: 基礎インフラ

| コンポーネント | 状態 | 備考 |
|---|---|---|
| Google Sheets 連携 (`src/sheets/`) | 稼働中 | Phase 8 タブ追加済み |
| X Publisher (`src/publishers/x_publisher.py`) | 稼働（dry_run） | 実投稿は環境フラグ必須 |
| Threads Publisher (`src/publishers/threads_publisher.py`) | 稼働（dry_run） | NotImplementedError for real post |
| Queue (`src/queue/`) | 稼働中 | WAITING_REVIEW / READY フロー |
| Approval flow (`src/approval/`) | 稼働中 | AI スコアリング含む |

---

## Phase 4〜6: Learning & PDCA

| コンポーネント | 状態 | 備考 |
|---|---|---|
| PDCA Orchestrator (`src/orchestrators/pdca_orchestrator.py`) | 稼働中 | auto_apply=False 必須 |
| Learning Rules (`src/learning/`) | 実装済み | `active=true` の自動化は禁止 |
| Weekly Growth Report | 実装済み | Sheets 出力のみ |
| Content Theme Guard (`src/generators/content_theme_guard.py`) | 稼働中 | |

---

## Phase 7: Orchestrators

| コンポーネント | 状態 | 備考 |
|---|---|---|
| `SourceToPostOrchestrator` | 稼働中 | Phase 11 テスト済み |
| `PDCAOrchestrator` | 稼働中 | Phase 10 テスト済み |
| `MediaIngestionOrchestrator` | 稼働中 | |
| `ThreadSeriesOrchestrator` | 稼働中 | |
| `OriginalHypothesisOrchestrator` | 稼働中 | |

---

## Phase 8: Source Registry + Operational Readiness

| コンポーネント | 状態 | 備考 |
|---|---|---|
| `source_registry.py` | 稼働中 | Phase 9 COLLECTION_METHODS 追加済み |
| `default_sources.json` | 稼働中 | Phase 9 フィールド追加済み |
| Content Mix Planner | 稼働中 | |
| End-to-End Preflight | 稼働中 | |

---

## 既知の技術的負債

### 未実装 (NotImplementedError)

```
src/publishers/threads_publisher.py:113  - 実 Threads 投稿
src/publishers/base.py:72               - abstract publish()
src/collectors/x_reference_collector.py:258,270 - X 収集実実装
```

### 設計上の制限

| 項目 | 現状 | 対応方針 |
|---|---|---|
| Cloudinary upload | dry_run のみ | `ALLOW_CLOUDINARY_UPLOAD=true` + confirm ゲート必須 |
| ffmpeg カット | 実装済みだが未テスト | `confirm_cut=True` ゲート追加 (Phase 13) |
| 実 LLM 生成 | `ALLOW_LLM_GENERATION` フラグ | 既存フロー維持 |
| note/article 収集 | 未実装 | Phase 13 `ArticleFetcher` 追加 |

---

## コード健全性サマリー (2025-12 時点)

- **Python ファイル数:** 67
- **テストスクリプト数:** 44
- **Phase 8-11 テスト:** FAIL=0
- **主要モジュール import エラー:** 修正済み（publishers/accounts 相対 import）

---

## 今後の優先事項

1. Phase 13: `ArticleFetcher` + `PipelineStore` + ToolDoctor
2. Phase 13: ソース候補 JSON 登録（night_scout / liver_manager / beauty_account）
3. Phase 14: 実 Threads / X 投稿パス（confirm + フラグ揃えた条件下のみ）
4. Phase 15: メディアアセット download/storage パイプライン
5. Phase 16: PDCA 本番連携

---

## 関連

- `docs/roadmap.md`
- `docs/operation-runbook.md`
- `docs/safety-guards.md`
