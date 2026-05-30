# 8:2 コンテンツ生成戦略

**更新日**: 2026-05-31

---

## 戦略概要

SNS投稿の生成を2つのモードに分ける:

| モード | 比率 | 説明 |
|---|---|---|
| `reference_based` | 80% | 収集した参考投稿の勝ち要素を活かしてリライト |
| `original_hypothesis` | 20% | アカウントのペルソナに基づいた独自仮説の投稿 |

### なぜ 8:2 か

- **reference_based 80%**: バズ実績のある投稿パターンを活用することで、安定した品質を確保する
- **original_hypothesis 20%**: 独自性・オリジナリティで差別化し、新規フォロワー獲得とペルソナの強化を狙う

---

## reference_based の流れ

```
reference_posts
  ↓ (収集: Phase 2.10)
reference_post_scores
  ↓ (分析: Phase 2.11)
generation_jobs
  ↓ (計画: Phase 2.13)
Gemini API call (reference_based_generator)
  ↓ (生成: Phase 2.14)
drafts (+ approval_score)
  ↓ (スコアリング: Phase 2.15)
queue
  ↓ (投稿: Phase 3)
posted_results
```

---

## 参考投稿の使い方

**模倣ではなく「勝ち要素の抽出と応用」**。

使うもの:
- `hook_style`: どのフック手法が効果的か（質問・驚き・共感・逆説など）
- `content_angle`: コンテンツの切り口（問題提起・体験談・比較・リスト等）
- `why_it_grew`: なぜバズったかの分析
- `replay_tip`: 再現のためのヒント

使わないもの:
- 元テキストの直接引用・模倣
- 著作権のある表現
- 特定個人・アカウントの特徴的な言い回し

---

## メディア戦略

`media_strategy` フィールドで管理:

| 値 | 説明 |
|---|---|
| `none` | テキストのみ |
| `reference_image` | 参考投稿のメディアを参照（URLのみ、リアップロードはせず利用判断） |
| `original_image` | オリジナル画像（将来: Canva/DALL-E等で生成） |

現フェーズでは `none` / `reference_image` のみ対応。

---

## 模倣リスク管理

`imitation_risk` が `high`（動画を含む参考投稿を元にした場合）は:
- `ai_publish_recommendation = review` に引き上げ
- 人間レビューを必須とする

---

## 品質ゲート

生成された投稿は以下の順序でチェックされる:

1. `text_policy`: 文字数チェック（FAIL → リライト最大2回）
2. `approval_scorer`: buzz/conversion/brand_risk スコア
3. `confidence_level`: HIGH/MEDIUM/LOW 判定
4. `ai_publish_recommendation`: recommend/review/reject
5. `auto_approve_threshold`: 閾値以上 → APPROVED、未満 → WAITING_REVIEW
