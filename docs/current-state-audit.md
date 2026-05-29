# 現状棚卸し監査レポート

**作成日**: 2026-05-29  
**対象**: v2 + X_autopost_yoru (feature/x-analysis-pipeline) + 既存3プロジェクト

---

## 現状の一言評価

> 既存 `X_autopost_yoru`（feature/x-analysis-pipeline）は収集・分析・生成パイプラインが完成。  
> v2 は投稿実行エンジン（安全ガード付き）が完成。  
> 両者は「分離した半完成品」であり、統合が最大の課題。

---

## v2 でできていること（Phase 1〜3-D 完了）

| カテゴリ | 実装内容 |
|---|---|
| Google Sheets接続 | `SheetsClient` + `MockSheetsClient` (12タブスキーマ) |
| Gemini下書き生成 | `draft_generator.py` + prompt_templates |
| Publisher基底 | `BasePublisher`, `PublishResult` dataclass |
| DryRunPublisher | 安全なdry-run実行 |
| XPublisher | tweepy OAuth1a / 3層環境変数ガード / 4層実行ガード |
| ThreadsPublisher | SafetyStop stub（Phase 3-F待ち） |
| Factory | `get_publisher(platform, dry_run)` |
| キューレビュー | `review_queue.py` (CLI表示・READY昇格) |
| キュー投稿 | `publish_queue.py` (4層ガード) |
| 承認フロー | `approve_queue.py` |
| 安全確認 | `phase3_safety_check.py` / `preflight_check.py` |
| テスト | Phase 2〜3-D 合計 **150 PASS / 0 FAIL** |
| ドキュメント | `docs/` 28ファイル以上 |

---

## v2 でできていないこと（未実装）

| カテゴリ | 内容 | 優先度 |
|---|---|---|
| Git管理 | → Phase 0 で解決 | 🔴 最高 |
| X収集パイプライン | `x_collect_posts.py` 相当 | 🔴 高 |
| X分析エンジン | `x_analyze_posts.py` 相当（スコアリング・リライト） | 🔴 高 |
| Reviewキュー同期 | `x_sync_post_queue.py` 相当 | 🟡 中 |
| Gemini生成（8:2） | `collect.py` 相当（original_hypothesis側） | 🟡 中 |
| メディア管理 | Cloudinaryアップロード・tweepy media_upload | 🟡 中 |
| Threads実投稿 | ThreadsPublisher 本実装 | 🟡 中 |
| AI自動判定 | 人間レビュー不要の自動承認フロー | 🟢 低 |
| GitHub Actions | 自動収集・分析・投稿 CI/CD | 🟡 中 |
| X認証情報 | Developer Portal設定・.env入力 | 🔴 高（Phase 3-D前提） |

---

## 既存 X_autopost_yoru でできていること（feature/x-analysis-pipeline）

### スクリプト群

| ファイル | 機能 | 状態 |
|---|---|---|
| `x_collect_posts.py` | X API収集（7監視アカウント + 2キーワード、6h増分） | ✅ 完成 |
| `x_analyze_posts.py` | パフォーマンス分析・バズ検出・Geminiリライト提案 | ✅ 完成 |
| `x_sync_post_queue.py` | 承認レビュー → 投稿キュー同期 | ✅ 完成 |
| `x_sheet_schema.py` | 6タブスプシスキーマ定義 | ✅ 完成 |
| `collect.py` | Geminiコンテンツ生成（original_hypothesis側） | ✅ 完成 |
| `x_pipeline_config.json` | 監視アカウント・キーワード・閾値設定 | ✅ 完成 |

### パフォーマンス計算式

```
performance_score = like_count
                  + (repost_count × 3)
                  + (reply_count × 2)
                  + (bookmark_count × 4)
                  + (impression_count / 100.0)
```

### バズ判定条件

- いいね数 ≥ 100、または
- インプレッション数 ≥ 10,000、または
- アカウント内上位20%、または
- キーワード群内上位20%

### スプシスキーマ（既存・6タブ）

| タブ名 | 役割 |
|---|---|
| 00_ダッシュボード | 分析サマリー |
| 01_収集投稿 | 収集投稿ビュー（39カラム） |
| 02_承認レビュー | 人間レビュー・リライト承認（25カラム） |
| 03_投稿キュー | 投稿待ちキュー（18カラム） |
| 98_収集内部 | 生データ（RAW_HEADERS 47カラム） |
| 99_システム | key/value状態管理 |

### GitHub Actions（既存・5 workflows）

| ワークフロー | スケジュール | 処理 |
|---|---|---|
| `x_collect_posts.yml` | 6時間おき | 収集 → 分析 → キュー同期 |
| `x_analyze_posts.yml` | 毎日 0:30 JST | 分析 → キュー同期 |
| `x_time_window.yml` | JST 13:45 / 17:45 | キューから自動投稿 |
| `collect.yml` | JST 22:00 毎日 | Gemini生成 → Sheets |
| `x_auto_post.yml` | 手動のみ | テスト投稿 |

---

## v2 と 既存X_autopost_yoru の差分分析

### スプシスキーマの違い

| 項目 | 既存（feature/x-analysis-pipeline） | v2（TAB_DEFINITIONS） |
|---|---|---|
| タブ数 | 6タブ | 12タブ |
| 承認フロー | Sheetsドロップダウン → `x_sync_post_queue.py` | `review_queue.py` CLI → `publish_queue.py` |
| キューID形式 | `x-{source_id}` | UUID形式 |
| 状態遷移語 | 投稿待ち / 投稿済み / スキップ / エラー | WAITING_REVIEW / READY / POSTED |
| 投稿管理粒度 | アカウント名文字列 | account_id参照 |

### 機能ギャップ一覧

| 機能 | 既存 | v2 |
|---|---|---|
| X収集 | ✅ | ❌ 未移植 |
| 分析・スコアリング | ✅ | ❌ 未移植 |
| Geminiリライト提案 | ✅ | ❌ 未移植 |
| キュー同期 | ✅ | ❌ 未移植 |
| Gemini自己生成（20%） | ✅ | ❌ 未移植 |
| X本番投稿（安全ガード付き） | ❌ | ✅ XPublisher完成 |
| Threads投稿 | ❌ | ✅ stub（3-F待ち） |
| 4層安全ガード | ❌ | ✅ 完備 |
| テスト | ❌ | ✅ 150 PASS |

---

## 8:2 投稿戦略 対応状況

| 戦略 | 既存X_autopost_yoru | v2 |
|---|---|---|
| 80% reference_based | ✅ 収集・分析・リライト提案まで実装済み | ❌ 未実装 |
| 20% original_hypothesis | ✅ collect.py (Gemini, 25カラムTSV) | ❌ 未実装 |
| 最終承認 | Sheetsドロップダウン（手動） | review_queue.py CLI（手動） |
| 自動投稿 | GitHub Actions (13:45/17:45 JST) | publish_queue.py（手動実行のみ） |

---

## 現在の完成度：約 45〜50%

```
[██████████░░░░░░░░░░] 50%

完成済み:
  ✅ 投稿実行エンジン（v2）
  ✅ 安全ガード体系（v2）
  ✅ 収集・分析・生成パイプライン（既存X_autopost_yoru）
  ✅ テスト体系（v2）

未完成:
  ❌ 既存パイプラインのv2への移植
  ❌ スプシスキーマ統合
  ❌ メディア管理（Cloudinary）
  ❌ X認証情報設定
  ❌ GitHub Actions CI/CD
  ❌ AI自動承認
```

---

## 次の推奨フェーズ

### 即時（Phase 0）
1. **v2 git init + GitHub新規リポジトリ作成** ← 現在実施中
2. **X Developer Portal 認証情報設定** → Phase 3-D 本番テストの前提

### 短期（Phase 2.x）
3. スプシスキーマ統合方針の決定（v2 12タブ維持 or 既存6タブ採用）
4. `x_collect_posts.py` → v2移植
5. `x_analyze_posts.py` → v2移植
6. `x_sync_post_queue.py` → v2移植
7. `collect.py` → v2移植（20% original_hypothesis）

### 中期（Phase 3-D〜F）
8. X 1件本番投稿テスト（認証情報設定後）
9. X メディア付き投稿（Phase 3-E）
10. Threads 本番投稿（Phase 3-F）

詳細は `docs/roadmap.md` を参照。
