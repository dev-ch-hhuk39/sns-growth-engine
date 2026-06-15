# AI Work Handoff

Codex / 別セッション Claude Code との引き継ぎ用ドキュメントです。  
**毎回の主要作業完了時に更新してください。**

---

## 最終更新

**2026-06-16** — Phase 13 コア実装完了 (FAIL=0)

---

## リポジトリ情報

- **GitHub:** `dev-ch-hhuk39/sns-growth-engine`
- **作業ディレクトリ:** `/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2`
- **最新コミット:** `7cb7d2fa` (feat: complete source-to-post automation foundation)

---

## システム概要

3アカウント（night_scout / liver_manager / beauty_account）向けの  
SNS 自動投稿システム。フルパイプライン:

```
Source候補 → fetch → BuzzScore → ReferencePost → MediaPlan
→ Generation → Preflight → PublishPlan → PDCA
```

---

## 現在のフェーズ状態

| フェーズ | 状態 | テスト |
|---|---|---|
| Phase 1〜8 | 完了 | FAIL=0 |
| Phase 9 (Fetcher基盤) | 完了 | 20 PASS |
| Phase 10 (Publishers/PDCA) | 完了 | 37 PASS |
| Phase 11 (Orchestrator) | 完了 | 10 PASS |
| Phase 12 (Docs/Config) | 完了 | FAIL=0 |
| **Phase 13 (Production readiness)** | **作業中** | - |

---

## Phase 13 完了状況（2026-06-16）

### A. ドキュメント系

- [x] `docs/ai-work-handoff.md`
- [ ] `docs/phase13-16-implementation-plan.md` — 未作成
- [ ] `docs/phase13-16-test-matrix.md` — 未作成
- [ ] `docs/production-readiness-audit.md` — 未作成
- [ ] `docs/source-fetcher-installation.md` — 未作成

### B. ToolDoctor ✅ 完了

- [x] `src/reference/fetchers/tool_doctor.py`
- [x] `scripts/check_source_fetcher_tools.py`
- [x] `scripts/test_phase13_tool_doctor.py` — PASS: 28 / FAIL: 0

### C. ソース候補 JSON ✅ 完了

- [x] `config/source_accounts/production_sources.example.json`
  - night_scout: 9 X + 9 YouTube = 18件 (全て candidate)
  - liver_manager: 7 YouTube + 6 note = 13件 (全て candidate)
  - beauty_account: 10 YouTube (candidate) + 7 TikTok (disabled) + 6 X (disabled) = 23件
  - 合計 54件 / 全て active=false, fetch_enabled=false
- [x] `scripts/test_phase13_production_sources.py` — PASS: 28 / FAIL: 0

### D-E. Source フィールド拡張 ✅ 完了

- [x] source_category / use_cases / subject_policy / candidate_status 全件設定済み

### F. ArticleFetcher ✅ 完了

- [x] `src/reference/fetchers/article_fetcher.py`
- [x] `src/reference/article_reference_normalizer.py`
- [x] `scripts/test_phase13_article_fetcher.py` — PASS: 21 / FAIL: 0
- [x] `scripts/test_phase13_article_normalizer.py` — PASS: 18 / FAIL: 0

### G. Source lifecycle CLI ✅ 完了

- [x] `scripts/add_source_candidate.py`
- [x] `scripts/update_source_status.py`
- [x] `scripts/review_source_candidates.py`
- [x] `scripts/test_phase13_source_lifecycle_cli.py` — PASS: 23 / FAIL: 0

### H-I. PipelineStore ✅ 完了

- [x] `src/storage/pipeline_store.py`
- [x] `scripts/save_pipeline_outputs.py`
- [x] `scripts/test_phase13_pipeline_store.py` — PASS: 15 / FAIL: 0

### J-K. Publisher CLI ✅ 完了

- [x] `scripts/publish_threads_post.py`
- [x] `scripts/publish_x_post.py`

### L. SmokePlan ✅ 完了

- [x] `scripts/run_phase13_smoke_plan.py`
- [x] `scripts/test_phase13_smoke_plan.py` — PASS: 15 / FAIL: 0

### M. Phase 13 全テスト FAIL=0 ✅

- 7 test files / 合計 PASS: 148 / FAIL: 0

### N. 残作業

- [ ] `docs/phase13-16-implementation-plan.md`
- [ ] `docs/phase13-16-test-matrix.md`
- [ ] `docs/production-readiness-audit.md`
- [ ] `docs/source-fetcher-installation.md`
- [ ] commit/push `feat: finalize production media source pipeline`

---

## 重要な安全制約

| 操作 | ゲート |
|---|---|
| 実 fetch | `confirm_fetch=True` 必須 |
| 動画 DL | `confirm_download=True` 必須 |
| ffmpeg カット | `confirm_cut=True` 必須 |
| Cloudinary upload | `confirm_upload=True` + `ALLOW_CLOUDINARY_UPLOAD=true` 必須 |
| 実投稿 | `confirm_post=True` + 環境フラグ必須 |
| beauty_account | 常に draft_only。active/READY/POSTED 化禁止 |

---

## アーキテクチャポイント

- `BaseFetcher.fetch()` → `FetchResult(status=OK/BLOCKED/NOT_INSTALLED/NOT_READY/WARN/ERROR)`
- `RawSourceItem`: 40+ field dataclass (`src/reference/fetchers/base_fetcher.py`)
- `SourceToPostOrchestrator.run()` → 8ステップ dict + safety dict
- `PDCAOrchestrator.run(results, account_id, platform, days, ...)` — `posted_results` / `dry_run` は引数名ではない
- `AccountConfig.is_active()` / `.is_draft_only()` — `.active` / `.draft_only` 属性は存在しない
- `PublishResult(platform=..., dry_run=..., success=..., message=...)` — platform は必須
- Publisher.publish シグネチャ: `publish(text, *, account: dict, derivative: dict, queue_item: dict, dry_run=True)`

---

## 既知の NotImplementedError

```
src/publishers/threads_publisher.py:113  — 実 Threads 投稿（意図的 block）
src/collectors/x_reference_collector.py:258,270 — X 収集実実装（Phase 13+ 対象）
```

---

## 次セッションへの引き継ぎ

1. `docs/phase13-16-implementation-plan.md` を作成
2. `config/source_accounts/production_sources.example.json` を作成（ソース候補全登録）
3. `src/reference/fetchers/tool_doctor.py` + `scripts/check_source_fetcher_tools.py` を作成
4. `src/reference/fetchers/article_fetcher.py` を作成（liver_manager の note ソース対応）
5. `src/storage/pipeline_store.py` を作成
6. 16 Phase 13 test scripts を作成し FAIL=0 まで修正
7. commit/push `feat: finalize production media source pipeline`
