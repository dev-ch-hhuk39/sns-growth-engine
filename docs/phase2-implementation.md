# Phase 2 実装内容

## 概要

Phase 2 では、Gemini を使ったコンテンツ生成パイプラインを実装しました。
本番SNS投稿はまだ行いません（Phase 3 で実装予定）。

---

## 実装ファイル一覧

### 新規作成

| ファイル | 役割 |
|---|---|
| `src/prompt_loader.py` | プロンプトテンプレートの取得・変数展開 |
| `src/draft_generator.py` | Gemini で SNS 下書きを生成する中核ロジック |
| `src/social_derivative_generator.py` | X / Threads 向け派生投稿生成ロジック |
| `src/queue_builder.py` | social_derivatives から queue を作るロジック |
| `scripts/generate_drafts.py` | 下書き生成 CLI |
| `scripts/generate_social_derivatives.py` | 派生投稿生成 CLI |
| `scripts/build_queue.py` | queue 構築 CLI |
| `scripts/run_pipeline.py` | パイプライン全体 CLI |
| `scripts/test_phase2.py` | Phase 2 動作確認テスト |

### 更新

| ファイル | 変更内容 |
|---|---|
| `src/sheets_client.py` | social_derivatives タブ追加・不足メソッド追加・MockSheetsClient 追加・make_client() 追加 |
| `src/llm_client.py` | MOCK_LLM 環境変数対応・platform-aware モック追加 |
| `src/main.py` | Phase 2 CLI オプション追加（--run-pipeline 等） |

---

## Phase 2 で実装した機能

1. **Gemini による draft 生成**
   - `draft_generator.generate_drafts()` で accounts → categories → prompts → Gemini → drafts の流れを実装
   - publish_decision でステータス判定（READY / DRAFT / HUMAN_REVIEW）

2. **X / Threads 向け派生投稿生成**
   - `social_derivative_generator.generate_social_derivatives()`
   - X は 120 文字以内に自動トリミング
   - Threads は 1行目フック＋2行空け＋本文フォーマット

3. **queue 構築**
   - `queue_builder.build_queue()`
   - auto_publish / min_publish_score / brand_risk_threshold を評価
   - scheduled_at は accounts.post_time / timezone から計算

4. **MockSheetsClient**
   - 認証情報なし・ネットワーク接続なしで動くモッククライアント
   - インメモリに書き込みを保持して reads でも返せる

5. **MOCK_LLM 対応**
   - `MOCK_LLM=true` で Gemini 呼び出しをモック化
   - DRY_RUN とは独立（DRY_RUN はシート書き込みも止める）

---

## 今回やっていないこと（Phase 3 以降）

- SNS への本番投稿（X API / Threads API）
- 投稿後インサイト自動取得
- category_scores 本格自動集計
- learning_rules 本格自動生成
- GitHub Actions 本番実行
