# 次フェーズ計画

## Phase 3: 本番投稿・計測・PDCA

### 目標

- X API / Threads API での実際の投稿
- 投稿後インサイト（いいね・インプレッション・フォロー）の自動取得
- category_scores の自動集計
- PDCA サイクルの自動化

---

### Phase 3 で実装すること

#### 1. X 投稿（X API v2）

- `src/x_publisher.py` を作成
- OAuth 2.0 認証
- queue.status=READY の derivative を取得して投稿
- 投稿後に queue.status=POSTED、posted_at を記録
- 失敗時は queue.status=FAILED、error を記録

#### 2. Threads 投稿（Threads API）

- `src/threads_publisher.py` を作成
- Meta Threads API（または Playwright fallback）
- queue.status=READY の derivative を取得して投稿

#### 3. 投稿後インサイト取得

- `src/insight_collector.py` を作成
- X API で likes / impressions / reposts を取得
- Threads API でインサイトを取得
- posted_results タブに保存

#### 4. category_scores 自動集計

- `src/category_scorer.py` を作成
- posted_results × content_categories を集計
- category_scores タブを更新

#### 5. learning_rules 自動生成

- Gemini にパフォーマンスデータを渡してインサイトを生成
- learning_rules タブに追加
- 次回のプロンプト生成に反映

#### 6. GitHub Actions 自動実行

- `.github/workflows/pipeline.yml` を作成
- スケジュール実行（例: 毎日 19:00 JST）
- Secrets から認証情報を注入

---

### Phase 3 の前提条件

- [ ] X Developer Account（v2 API アクセス）取得
- [ ] Threads API アクセス取得（またはPlaywright環境整備）
- [ ] accounts.auto_publish を TRUE に更新（現在は FALSE）
- [ ] SNS_MASTER_SHEET_ID と認証情報を GitHub Secrets に設定
- [ ] Phase 2 パイプラインの dry-run で動作確認済み

---

### 優先順位

1. X 投稿（最小構成で実装）
2. 投稿後インサイト取得
3. Threads 投稿
4. category_scores 自動集計
5. learning_rules 自動生成
6. GitHub Actions 自動化

---

### 注意事項

- Phase 3 実装前に必ず Phase 2 の dry-run を完全に通すこと
- accounts.auto_publish はデフォルト FALSE のまま開発し、本番投稿直前に TRUE に変更する
- 本番投稿前にスプレッドシートの queue タブを目視確認すること
- X API の Rate Limit に注意（v2 Free は制限が厳しい）
