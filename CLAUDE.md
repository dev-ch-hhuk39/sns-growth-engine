# SNS自動投稿システム v2 — プロジェクト CLAUDE.md

## グローバル方針の参照

グローバルの Model / Subagent Operating Policy は `~/.claude/CLAUDE.md` を参照してください。
このプロジェクトもグローバル方針に従います。

- Fable 5 が使える場合: 設計・監査・レビュー・最終判断に使う
- 使えない場合は Opus
- 実装・テスト修正・反復修正は Sonnet 中心
- CodeGraph / context-mode / Headroom の運用方針はグローバル方針に従う

---

## プロジェクト固有の安全ルール（グローバル方針より優先）

以下はプロジェクト固有のルールです。グローバル方針よりも優先されます。

### 絶対禁止（コードやCLIでも実行しない）

- SNS本番投稿（X / Threads）
- X API / Threads API 実呼び出し
- Cloudflare API 実呼び出し
- Cloudinary 実upload（ALLOW_CLOUDINARY_UPLOAD=true 明示前）
- 外部URLからの実download（--confirm-download なし）
- YouTube / TikTok 本番大量取得
- 長尺動画download
- ffmpeg 実切り抜き（ローカル確認済みファイル以外）
- GitHub Actions 実行
- Hermes Agent インストール
- Codex 利用
- scraping / 規約違反取得
- 機密情報（APIキー・トークン・.env中身）の表示

### 環境変数フラグ（これらをtrueにしない）

- `PUBLISH_ENABLED=true`
- `ALLOW_REAL_X_POST=true`
- `ALLOW_REAL_THREADS_POST=true`
- `ALLOW_TRANSCRIPTION_API=true`
- `ALLOW_CLOUDINARY_UPLOAD=true`

### アカウント安全ルール

- `beauty_account` は draft_only のまま
- `beauty_account` の active化 / READY化 / 実投稿は禁止
- `beauty_account` の活性化条件は `docs/beauty-account-activation-checklist.md` 参照
- `posted_results` へ本番投稿結果を書かない
- `queue.status` を POSTED にしない
- `learning_rules.active` を自動で true にしない
- `source priority` を自動変更しない（改善提案はWAITING_REVIEW）
- `prompt / code` の自動書き換え禁止

---

## Phase状況

- Phase 1〜6: 完了
- Phase 7: Phase 7オーケストレーター5本 完了（08f5ac1）
- Phase 8: operational readiness hardening + Source Registry（本フェーズ）

### Phase 8 追加機能

- Source Account / Video Source Registry (`src/reference/source_registry.py`)
- content_mix_planner → generation_jobs候補出力
- source_account_collector → source_registry連携
- media_ingestion_pipeline → source_registry連携
- end_to_end_publish_preflight → source rights確認追加
- pdca_orchestrator → source別分析・次回plan追加
- Sheets schema Phase 8タブ追加
- preflight_real_llm_generation（実LLM生成前チェック）
- check_beauty_activation_readiness（活性化条件チェック）

---

## source registry 運用方針

- `config/source_accounts/default_sources.json` で管理
- 実API取得 / scraping / download は禁止
- 手動JSON/CSV/URL投入が安全な基本ルート
- `target_account_ids` でどのアカウントに使うかを紐付ける
- `rights_policy=unknown` は WAITING_REVIEW 必須
- `media_policy=do_not_download` は download 禁止
- `media_policy=plan_only` は Cloudinary upload 禁止
- `reuse_policy=no_reuse` は media 利用禁止
- source priority 変更は改善提案のみ（自動変更禁止）

---

## ドキュメント

主要ドキュメント:
- `docs/roadmap.md` — Phase別ロードマップ
- `docs/reference-pipeline-runbook.md` — 参考収集/採点/動画/切り抜き/投稿案の標準CLI運用
- `docs/source-account-registry.md` — source registry設計
- `docs/operation-runbook.md` — 運用手順
- `docs/manual-smoke-test-sequence.md` — スモークテスト手順
- `docs/end-to-end-publish-preflight.md` — 実投稿前チェック
- `docs/beauty-account-activation-checklist.md` — beauty_account活性化条件
- `docs/beauty-account-roadmap.md` — beauty_accountロードマップ
- `docs/real-llm-generation-test.md` — 実LLM生成テスト手順

---

## テスト実行

```bash
# Phase 8 テスト
python3 scripts/test_phase8_sheets_schema.py
python3 scripts/test_source_account_registry.py
python3 scripts/test_phase8_source_registry_to_collection.py
python3 scripts/test_phase8_content_mix_to_jobs.py
python3 scripts/test_phase8_source_to_reference_generation.py
python3 scripts/test_phase8_media_to_preflight.py
python3 scripts/test_phase8_end_to_end_preflight_matrix.py
python3 scripts/test_phase8_pdca_to_next_plan.py
python3 scripts/test_real_llm_generation_preflight.py
python3 scripts/test_phase8_real_llm_generation_safety.py
python3 scripts/test_beauty_activation_readiness.py
```
