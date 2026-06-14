# Buzz Scoring（Phase 9）

## 概要

`src/reference/buzz_scorer.py` が実装するバズスコアリング機能。

RawSourceItem のエンゲージメント指標を 0.0〜1.0 に正規化し、投稿の「伸び」を定量評価する。

## スコア算出ロジック

```
buzz_score = Σ(weight_i × log_norm(metric_i, ceiling_i))
```

### プラットフォーム別ウェイト

| プラットフォーム | like | view | repost | bookmark |
|---|---|---|---|---|
| YouTube | 0.1 | 0.6 | 0.1 | 0.1 |
| TikTok | 0.15 | 0.5 | 0.15 | 0.1 |
| X / Twitter | 0.35 | 0.2 | 0.3 | 0.1 |
| Threads | 0.4 | 0.2 | 0.3 | 0.05 |
| default | 0.25 | 0.35 | 0.2 | 0.1 |

### log_norm

```python
def _log_norm(value, ceiling):
    return min(math.log1p(value) / math.log1p(ceiling), 1.0)
```

メトリクスが 0 でもスコア 0 になるだけで例外は発生しない。

## 使い方

```python
from src.reference.buzz_scorer import score_items, filter_top_items

scored = score_items(items, source_platform="youtube", top_n=5)
top = filter_top_items(scored, min_buzz_score=0.3, top_n=10)
```

## 返り値フィールド

| フィールド | 説明 |
|---|---|
| buzz_score | 0.0〜1.0 スコア |
| buzz_rank | 1 始まりランク（低い = 高スコア） |
| is_top_post | top_n 内なら True |
| why_it_grew | バズ理由テキスト（自動生成） |
| replay_tip | 再現ヒント（自動生成） |
| recommended_generation_mode | reference_based / original_hypothesis / video_reference |

## 注意事項

- スパースメトリクス（値が 0 だらけ）でもエラーにならない
- `ceiling` は プラットフォーム別デフォルト値（YouTube: views=1_000_000、X: likes=5_000 など）
- スコアリングは投稿の相対評価であり、絶対的な品質判断ではない
