# v2 X パイプライン統合計画

**作成日**: 2026-05-29

---

## 統合方針

既存 `X_autopost_yoru/feature/x-analysis-pipeline` の資産を、v2 の設計（SheetsClient / Publisher / Queue）に合わせて移植する。

**原則**:
- 既存コードの「勝ちロジック」（性能計算・分類・リライト）はほぼそのまま移植する
- スプシアクセスは全て v2 SheetsClient に統一する
- 安全ガードは v2 の4層構造を維持する
- 実 Sheets への書き込みは dry_run=True がデフォルト

---

## 8:2 投稿生成方針

```
全投稿の 80% = reference_based
               収集した参考投稿の「勝ち要素」をGeminiが再構成
全投稿の 20% = original_hypothesis
               Gemini が content_categories / learning_rules / posted_results を
               参照しアカウントトンマナで自走生成
```

### reference_based フロー

```
reference_sources
      ↓ X API収集（6h増分）
reference_posts（raw保存）
      ↓ performance_score / hook_style / content_angle
reference_post_scores
      ↓ バズ閾値フィルタ + Gemini再構成
social_derivatives（WAITING_REVIEW）
      ↓ 人間 or AI承認
queue（READY）
      ↓ publish_queue.py + XPublisher
POSTED + posted_results
```

### original_hypothesis フロー

```
content_categories + learning_rules + posted_results
      ↓ Gemini（アカウントトンマナ）
drafts（WAITING_REVIEW）
      ↓ generate_social_derivatives → social_derivatives
queue（READY）
      ↓ publish_queue.py + XPublisher
POSTED + posted_results
```

---

## 移植計画（フェーズ別）

### Phase 2.8（現在）: 設計・スタブ・スキーマ追加
- docs 整備
- TAB_DEFINITIONS に media_assets / reference_post_scores / generation_jobs 追加
- src/collectors / analyzers / media / generation ディレクトリ作成（スタブ）
- generation_planner.py 最小実装
- text_policy.py 実装
- config/reference_sources.example.json 作成
- test_phase28.py 追加

### Phase 2.9（次）: スキーマ Sheets 反映
- setup_sheets.py 実行で実 Sheets に新タブを追加
- 既存データとの整合確認

### Phase 2.10: X reference collector 移植
- `x_collect_posts.py` → `src/collectors/x_reference_collector.py`
- v2 SheetsClient を使用するよう修正
- reference_posts タブへの書き込み

### Phase 2.11: X analyzer 移植
- `x_analyze_posts.py` → `src/analyzers/reference_post_analyzer.py`
- reference_post_scores タブへのスコア書き込み
- Gemini リライト提案の統合

### Phase 2.12: Cloudinary media_assets 統合
- `src/media/cloudinary_client.py` 実装
- media_assets タブへの保存
- reuse_risk / imitation_risk の判定ロジック

### Phase 2.13: 8:2 generation planner（本格実装）
- generation_jobs タブへの計画書き込み
- reference_based / original_hypothesis の分岐実装

### Phase 2.14: reference_based Gemini prompt
- リライト用プロンプトテンプレート作成
- Gemini 再構成呼び出し統合

### Phase 2.15: AI 承認スコアリング
- approve_queue.py への AI スコア統合
- 閾値に基づく自動承認

### Phase 2.16: 文字数制限強化
- text_policy.py の Gemini プロンプトへの組み込み
- 生成後の自動検証

---

## 文字数制限ポリシー

| プラットフォーム | 推奨上限 | ハード上限 | 超過時の扱い |
|---|---|---|---|
| X | 120文字 | 140文字 | 121〜140: WARN/needs_rewrite, 141+: FAIL |
| Threads | 600文字 | 800文字 | 601〜800: WARN, 801+: FAIL |

Threads フォーマット: `フック（1行）\n\n本文（残り）`

---

## メディア管理方針（Cloudinary）

```
X API / 既存URL（image_urls / video_urls）
      ↓ download_media()（requests / yt-dlp）
      ↓ upload_to_cloudinary()
media_assets タブ
  - original_media_url（元URL）
  - storage_url（Cloudinary URL）
  - cloudinary_public_id
  - media_type（image / video）
  - reuse_status（available / used / restricted）
  - imitation_risk（low / medium / high）
  - used_count（転載回数）
```

**imitation_risk 判定方針**:
- `low`: オリジナル性が高く類似投稿が少ない
- `medium`: 複数アカウントが類似投稿
- `high`: ほぼ同一テキスト・メディアが存在する

---

## 人間判断 → AI判定への移行方針

| 判定項目 | 現状（人間） | 将来（AI） | 移行フェーズ |
|---|---|---|---|
| 転載可否 | Sheets ドロップダウン | imitation_risk 自動判定 | Phase 2.12 |
| 投稿可否 | Sheets ドロップダウン | AI 承認スコア | Phase 2.15 |
| 採用案A/B | Sheets ドロップダウン | 品質スコア自動選択 | Phase 2.15 |
| 投稿タイミング | 手動スケジュール | distribution_rules + 実績 | Phase 4 |

---

## 既存スクリプト移植先マッピング

| 既存スクリプト（X_autopost_yoru） | v2 移植先 |
|---|---|
| `x_collect_posts.py` | `src/collectors/x_reference_collector.py` |
| `x_analyze_posts.py` | `src/analyzers/reference_post_analyzer.py` |
| `x_prepare_media_assets.py` | `src/media/cloudinary_client.py`（新規） |
| `x_sync_post_queue.py` | `scripts/sync_reference_queue.py`（新規） |
| `auto_post.py` | `scripts/publish_queue.py`（既存）で代替 |
| `x_sheet_schema.py` | `src/sheets_client.py` TAB_DEFINITIONS へ統合 |
| `x_pipeline_config.json` | `config/reference_sources.example.json` |
| `.github/workflows/x_collect_posts.yml` | `.github/workflows/`（Phase 2.x 完了後） |
