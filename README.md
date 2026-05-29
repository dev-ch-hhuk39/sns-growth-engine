# sns-growth-engine

SNS growth automation engine for collection, analysis, generation, approval, publishing, and learning.

## 目的

X (Twitter) / Threads を対象に、SNS投稿の**収集・分析・生成・承認・投稿・結果学習**を自動化するエンジン。

- 収集したバズ投稿を分析・スコアリングし、AIでリライト提案
- Geminiで独自仮説コンテンツを生成
- 人間の承認フロー → 投稿キュー → 安全ガード付き本番投稿
- 投稿結果を収集しフィードバックループへ

## 対象アカウント

| アカウントID | 用途 |
|---|---|
| `night_scout` | 夜職ジャンル |
| `liver_manager` | ライバージャンル |

## 現在の実装状況（Phase 1〜3-D 完了）

| Phase | 内容 | 状態 |
|---|---|---|
| Phase 1 | Gemini下書き生成 | ✅ 完了 |
| Phase 2 | Google Sheets接続・12タブスキーマ・queue/review | ✅ 完了 |
| Phase 3-A | Publisher Interface (BasePublisher / DryRunPublisher) | ✅ 完了 |
| Phase 3-B | 承認フロー (approve_queue) | ✅ 完了 |
| Phase 3-C | キュー投稿基盤 (publish_queue dry-run / review_queue) | ✅ 完了 |
| Phase 3-D | XPublisher 実装 (tweepy OAuth1a / 4層安全ガード) | ✅ 完了 |
| Phase 3-E | X メディア付き投稿 | 🔜 次フェーズ |
| Phase 3-F | Threads 本番投稿 | 🔜 次フェーズ |

**テスト**: Phase 2〜3-D 合計 **150 PASS / 0 FAIL**

## 既存 X_autopost_yoru から統合予定の資産

| ファイル | 内容 |
|---|---|
| `x_collect_posts.py` | X API収集（監視アカウント・キーワード） |
| `x_analyze_posts.py` | パフォーマンス分析・スコアリング・Geminiリライト |
| `x_prepare_media_assets.py` | メディア資産管理（Cloudinary連携） |
| `x_sync_post_queue.py` | 承認レビュー → 投稿キュー同期 |
| `auto_post.py` | テキスト時刻スロット投稿 |

## 投稿戦略方針

- **80% reference_based**: 収集したバズ投稿を分析・リライトして参考投稿
- **20% original_hypothesis**: Geminiが独自仮説・インサイトを生成して投稿
- Cloudinary でメディア資産を一元管理
- AI承認スコアリングで人間レビューを支援

## 安全ガード

本番投稿には以下の4層ガードが必要です（デフォルトはすべてfalse）。

```
PUBLISH_ENABLED=false          # Layer 1: 全投稿の大元スイッチ
ALLOW_REAL_X_POST=false        # Layer 2: X投稿専用スイッチ
ALLOW_REAL_THREADS_POST=false  # Layer 2: Threads投稿専用スイッチ
--confirm-real-post            # Layer 3: publish_queue.py 実行時フラグ
--max-real-posts 1             # Layer 4: 最大投稿件数上限
```

## セットアップ概要

```bash
# 1. 依存パッケージ
pip install -r requirements.txt

# 2. 環境変数の設定
cp .env.template .env
# .env を編集して各APIキーを設定

# 3. 動作確認
python scripts/preflight_check.py

# 4. 安全確認
PYTHONPATH=src python3 scripts/phase3_safety_check.py
```

## テストコマンド

```bash
PYTHONPATH=src python3 scripts/test_phase2.py
PYTHONPATH=src python3 scripts/test_phase3a.py
PYTHONPATH=src python3 scripts/test_phase3b.py
PYTHONPATH=src python3 scripts/test_phase3c.py
PYTHONPATH=src python3 scripts/test_phase3d.py
PYTHONPATH=src python3 scripts/phase3_safety_check.py
PYTHONPATH=src python3 scripts/preflight_check.py
```

## 絶対にコミットしてはいけないもの

- `.env`（APIキー・Sheetsシークレットが含まれる）
- `GCP_SA_JSON` / `SA_JSON_BASE64`（Google Cloud サービスアカウント）
- `GEMINI_API_KEY`
- X API Key / Access Token / Secret
- Threads アクセストークン
- Cloudinary API Secret
- `*.json`（サービスアカウントJSONなど）
- `*.pem` / `*.key` / `*.b64`

設定例は `.env.template` を参照してください。

## ドキュメント

詳細なドキュメントは `docs/` ディレクトリを参照してください。

| ドキュメント | 内容 |
|---|---|
| `docs/roadmap.md` | フェーズ別実装ロードマップ |
| `docs/current-state-audit.md` | 現状棚卸しと差分分析 |
| `docs/security-and-secrets.md` | シークレット管理方針 |
| `docs/safety-guards.md` | 安全ガード詳細 |
| `docs/phase3d-x-manual-post.md` | X手動投稿テスト手順 |
| `docs/x-publisher-setup.md` | X Developer Portal設定手順 |
