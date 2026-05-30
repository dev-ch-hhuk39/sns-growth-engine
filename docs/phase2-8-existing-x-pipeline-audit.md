# Phase 2.8 既存 X パイプライン 監査レポート

**作成日**: 2026-05-29  
**対象**: X_autopost_yoru / feature/x-analysis-pipeline

---

## 各ファイルの役割と移植評価

### x_collect_posts.py — X投稿収集

**役割**: X API から監視アカウント・キーワードの投稿を収集し Google Sheets へ書き込む。

| 関数 / 処理 | 移植評価 | 備考 |
|---|---|---|
| `load_config()` | ✅ そのまま移植可 | v2 config 構造に合わせて path 調整 |
| `parse_args()` | 🔄 再設計 | v2 の CLI 規約に合わせる |
| `normalize_post()` | ✅ そのまま移植可 | RAW_HEADERS → v2 reference_posts スキーマに変換 |
| `fetch_account_posts()` | ✅ そのまま移植可 | X Bearer Token 必須 |
| `upsert_raw_sheet()` | 🔄 再設計 | v2 SheetsClient.upsert 方式に合わせる |
| `bootstrap / ensure_headers` | ❌ 不要 | v2 setup_all() で一元管理 |

**依存**: `x_sheet_schema.py`, `x_sheet_utils.py`, `x_pipeline_config.json`

---

### x_analyze_posts.py — パフォーマンス分析・AI分析

**役割**: 収集済み投稿をスコアリングし、Gemini でリライト提案を生成して承認レビュータブへ書き出す。

| 関数 / 処理 | 移植評価 | 備考 |
|---|---|---|
| `build_dataframe()` | ✅ そのまま移植可 | pandas 依存。v2 reference_post_scores に対応 |
| `performance_score` 計算 | ✅ そのまま移植可 | `like + repost×3 + reply×2 + bookmark×4 + impression/100` |
| `detect_content_angle()` | ✅ そのまま移植可 | 体験談/ノウハウ/暴露/共感/質問/その他 |
| `detect_hook_style()` | ✅ そのまま移植可 | リスト型/質問型/暴露型/体験談型/断定型 |
| `why_it_grew()` | ✅ そのまま移植可 | バズ理由の文字列生成 |
| `replay_tip()` | ✅ そのまま移植可 | 再現ポイントの文字列生成 |
| `rewrite_light()` | ✅ そのまま移植可 | 軽整形リライト（Gemini不使用） |
| `rewrite_reframe()` | ✅ そのまま移植可 | 再構成リライト（Gemini不使用） |
| `build_review_rows()` | 🔄 再設計 | v2 queue スキーマに変換する必要あり |
| `build_collection_rows()` | 🔄 再設計 | v2 reference_post_scores に対応 |
| `build_insights()` | 🟡 後回し | Phase 4 のダッシュボード相当 |

**依存**: `pandas`, Gemini（リライト提案は将来版）, `x_sheet_schema.py`

---

### x_prepare_media_assets.py — メディア資産管理

**役割**: feature/x-analysis-pipeline ブランチには**存在しない**（未実装）。  
v2 で新規実装が必要。

| 処理 | 方針 |
|---|---|
| 画像ダウンロード | requests + yt-dlp (動画) |
| Cloudinaryアップロード | cloudinary SDK |
| media_assets タブへ保存 | v2 SheetsClient 経由 |
| reuse_risk 判定 | imitation_risk カラム（手動 or AI判定） |

---

### x_sync_post_queue.py — 承認レビュー → 投稿キュー同期

**役割**: `02_承認レビュー` タブの承認済み行を読み取り `03_投稿キュー` タブへ同期する。

| 関数 / 処理 | 移植評価 | 備考 |
|---|---|---|
| `pick_selected_text()` | ✅ そのまま移植可 | 採用案A/B の選択ロジック |
| `first_media_url()` | ✅ そのまま移植可 | `|` 区切りURLの先頭を取得 |
| `build_queue_rows()` | 🔄 再設計 | v2 queue スキーマ（WAITING_REVIEW→READY）に合わせる |
| `run()` | 🔄 再設計 | v2 SheetsClient を使用 |

**承認条件**: 転載OK + 投稿OK + 採用案(A/B)選択 + 投稿対象が「投稿する」

---

### auto_post.py (main branch) — テキスト時刻スロット投稿

**役割**: 時刻スロット（00:00/03:00/.../21:00）に基づいてX投稿を実行する。

**移植評価**: ❌ v2 では `publish_queue.py` + `XPublisher` に置き換えるため**不要**。

---

### x_sheet_schema.py — スプシスキーマ定義

**役割**: 既存 6タブのヘッダー定義・ドロップダウン定義を一元管理。

**移植評価**: v2 `sheets_client.py` の `TAB_DEFINITIONS` に統合済み（設計思想は共通）。  
新タブ（media_assets / reference_post_scores / generation_jobs）を TAB_DEFINITIONS へ追加することで吸収。

---

### x_pipeline_config.json — パイプライン設定

**役割**: 監視アカウント・キーワード・収集間隔・バズ閾値を定義。

**移植評価**: ✅ v2 の `config/reference_sources.example.json` として移植。  
`account_id` を追加し、マルチアカウント対応にする。

---

### .github/workflows/x_collect_posts.yml — GitHub Actions

**役割**: 6時間おきに収集→分析→キュー同期を自動実行。

**移植評価**: 🔄 Phase 2.x 完了後に v2 用として再設計。  
今回はまだ実行しない。

---

## 既存 feature/x-analysis-pipeline でできていること

- ✅ X API からの監視アカウント・キーワード収集（6h 増分）
- ✅ performance_score 計算（like + repost×3 + reply×2 + bookmark×4 + impression/100）
- ✅ content_angle / hook_style の自動分類
- ✅ バズ判定（いいね≥100 or impression≥10,000 or 上位20%）
- ✅ rewrite_light / rewrite_reframe（Geminiなしのルールベース）
- ✅ 02_承認レビュータブへのリライト案書き出し
- ✅ 03_投稿キューへの同期（承認条件チェック付き）
- ✅ GitHub Actions CI/CD（collect / analyze / auto_post）
- ✅ Sheetsドロップダウン承認フロー

## v2 でできていること

- ✅ Google Sheets 12タブスキーマ
- ✅ Gemini 下書き生成
- ✅ XPublisher（tweepy OAuth1a / 4層安全ガード）
- ✅ ThreadsPublisher（stub）
- ✅ キューライフサイクル（WAITING_REVIEW→READY→POSTED）
- ✅ review_queue / approve_queue / publish_queue（CLI）
- ✅ MockSheetsClient（テスト用）
- ✅ 150 PASS テスト

## v2 に足りないもの

- ❌ X API 収集コレクター（reference collector）
- ❌ パフォーマンス分析・スコアリング
- ❌ メディア資産管理（Cloudinary）
- ❌ 承認レビュー → キュー同期の自動化
- ❌ 8:2 生成プランナー
- ❌ 文字数ポリシー（X: 120/140字、Threads: 600〜800字）
- ❌ reference_posts スコアタブ（reference_post_scores）
- ❌ media_assets タブ
- ❌ generation_jobs タブ
- ❌ GitHub Actions（収集・分析・自動生成）
