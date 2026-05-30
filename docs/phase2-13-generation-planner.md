# Phase 2.13: 8:2 Generation Planner

**フェーズ**: 2.13  
**ステータス**: 実装中  
**目的**: 80% reference_based / 20% original_hypothesis の投稿比率を管理する生成計画システム

---

## 概要

`generation_jobs` タブを起点に、1日あたりの投稿生成数と手法比率を管理する。  
`reference_post_scores` を参照し、スコアの高い参考投稿を優先的に選択する。

---

## 8:2 比率ルール

| 生成モード | 割合 | 説明 |
|---|---|---|
| `reference_based` | 80% | 参考投稿の勝ち要素をリライト |
| `original_hypothesis` | 20% | 独自仮説・トレンドをゼロから生成 |

`daily_target_count = 3` の場合:
- reference_based: 2件（`round(3 × 0.8)` = 2.4 → 2）
- original_hypothesis: 1件（3 - 2 = 1）

`daily_target_count = 10` の場合:
- reference_based: 8件
- original_hypothesis: 2件

---

## generation_jobs タブの役割

各アカウント × プラットフォームの生成ルールを定義する。  
1レコード = 1つの生成計画ジョブ。

### 主要フィールド

| フィールド | 説明 |
|---|---|
| `job_id` | UUID |
| `account_id` | v2アカウントID |
| `platform` | `x` / `threads` |
| `generation_mode` | `reference_based` / `original_hypothesis` / `mixed` |
| `reference_based_ratio` | 0.8 |
| `original_hypothesis_ratio` | 0.2 |
| `daily_target_count` | 1日あたり生成目標件数 |
| `min_reference_score` | 参考投稿の最低スコア閾値（デフォルト50.0） |
| `status` | `pending` / `in_progress` / `done` / `failed` |
| `reference_post_id` | 使用した参考投稿ID |
| `reference_post_score_id` | 使用したスコアレコードID |
| `media_asset_id` | 使用したメディアアセットID（任意） |
| `generated_draft_id` | 生成された下書きID |
| `generated_at` | 生成完了日時 |

---

## 参考候補選択ロジック

1. `reference_post_scores` から `account_id` が一致するレコードを取得
2. `buzz_score >= min_reference_score` でフィルタ
3. `buzz_score` 降順で `daily_target_count × 2` 件をバッファとして取得
4. ランダムサンプリングで `reference_count` 件を選択（多様性確保）
5. `max_reference_reuse_per_source` 以上使用済みの参考投稿を除外

---

## 実装ファイル

- `src/generation/generation_planner.py` — 本体
- `scripts/plan_generation_jobs.py` — CLI

---

## 関連フェーズ

- Phase 2.11: reference_post_scores（入力元）
- Phase 2.12: media_assets（メディア情報参照）
- Phase 2.14: reference_based_generator（出力先）
