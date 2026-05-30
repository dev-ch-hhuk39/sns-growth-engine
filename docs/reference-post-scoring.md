# 参考投稿スコアリング 仕様

**最終更新**: 2026-05-30

---

## 概要

収集した参考投稿（`reference_posts` タブ）に対してパフォーマンス分析を行い、`reference_post_scores` タブにスコアを保存する。

分析エンジン: `src/analyzers/reference_post_analyzer.py`

---

## performance_score 計算式

```
performance_score = likes + reposts×3 + reply_count×2 + bookmark_count×4 + impressions/100
```

### 重み付けの意図

| 指標 | 重み | 理由 |
|---|---|---|
| likes | ×1 | 基本エンゲージメント |
| reposts | ×3 | 拡散力が高い（いいねより価値が高い） |
| reply_count | ×2 | 会話促進 |
| bookmark_count | ×4 | 保存 = 強い購買・行動意向 |
| impressions | ÷100 | 大きな数値を正規化してスコアに加算 |

---

## buzz_score

```
buzz_score = min(100.0, performance_score / 500 × 100)
```

- `500` が `buzz_score = 100` の閾値（DEFAULT_THRESHOLDS で変更可能）
- スコアが 500 以上なら buzz_score = 100.0 に上限制御
- 0〜100 のスケールで投稿の「バズ度」を表す

---

## account_percentile / keyword_percentile

同一グループ内でのパフォーマンス相対評価。

- `account_percentile`: 同じ `account_id` 内でのパーセンタイル順位
- `keyword_percentile`: 同じ `keywords`（パイプ区切り）内でのパーセンタイル順位
  - keywords が空の場合は「キーワードなし」グループとして扱う

計算方式: pandas の `rank(pct=True, method='average')` 相当

```
percentile = (下回る件数 + 同値件数×0.5) / 総件数
```

---

## content_angle（切り口分類）

投稿テキスト全体からキーワードマッチングで分類する。

| 分類 | キーワード（いずれか含む） |
|---|---|
| 体験談 | 実際・体験・経験・昔・わたし・自分 |
| ノウハウ | 方法・コツ・やり方・ポイント・攻略 |
| 暴露 | 裏・暴露・本音・闇・ぶっちゃけ |
| 共感 | あるある・つらい・わかる・共感・しんどい |
| 質問 | ?・？・どう思う・教えて・ありますか |
| その他 | （上記に該当しない） |

---

## hook_style（書き出し型分類）

`extracted_hook`（なければ `text`）の冒頭から分類する。

| 分類 | 判定条件 |
|---|---|
| リスト型 | 冒頭が `【`/`[`/`1.`/`1 `/`・` で始まる |
| 質問型 | 冒頭40字以内に `?` または `？` |
| 暴露型 | 冒頭40字以内に `実は`/`ぶっちゃけ`/`正直`/`結論` |
| 体験談型 | 冒頭40字以内に `今日`/`昨日`/`この前`/`さっき` |
| 断定型 | 上記に該当しない（デフォルト） |
| 不明 | テキストが空 |

---

## media_label

`media_urls`（パイプ区切り文字列）から判定する。

| 値 | 判定条件 |
|---|---|
| 動画あり | `.mp4`/`.mov`/`amplify_video` が含まれる |
| 画像あり | media_urls が空でない（動画でない） |
| メディアなし | media_urls が空または None |

---

## text_length_bucket

投稿テキスト長から4区分に分類する。

| 区分 | 文字数 |
|---|---|
| 短文(0-60字) | 0〜60字 |
| 中短文(61-120字) | 61〜120字 |
| 中文(121-180字) | 121〜180字 |
| 長文(181字以上) | 181字以上 |

---

## why_it_grew（伸びた理由）

以下の条件を全て評価して、該当するものを読点区切りで返す。

| 条件 | 出力 |
|---|---|
| likes >= buzz_like_count（デフォルト100） | いいね100以上 |
| impressions >= buzz_impression_count（デフォルト10000） | インプレッション10000以上 |
| media_label == 動画あり | 動画あり |
| media_label == 画像あり | 画像あり |
| account_percentile >= 0.8 | 同一アカウント内で上位20% |
| keyword_percentile >= 0.8 | 同一キーワード群で上位20% |

---

## replay_tip（再現ポイント）

分析結果から再現のポイントを「 / 」区切りで返す。

```
例: 質問型の書き出し / ノウハウの切り口 / 画像付き / 中短文(61-120字)
```

time_slot（投稿時間帯）は v2 では対象外（旧実装から削除）。

---

## reference_post_scores カラム

| カラム | 説明 |
|---|---|
| `score_id` | UUID（自動生成） |
| `reference_post_id` | reference_posts.id への外部参照 |
| `account_id` | v2 アカウントID |
| `performance_score` | 総合スコア |
| `buzz_score` | バズ度（0〜100） |
| `like_score` | likes のスコア寄与（= likes） |
| `reply_score` | reply_count×2 |
| `repost_score` | reposts×3 |
| `bookmark_score` | bookmark_count×4 |
| `impression_score` | impressions/100 |
| `account_percentile` | アカウント内パーセンタイル（0.0〜1.0） |
| `keyword_percentile` | キーワード群内パーセンタイル（0.0〜1.0） |
| `why_it_grew` | 伸びた理由（読点区切り） |
| `replay_tip` | 再現ポイント（/ 区切り） |
| `hook_style` | 書き出し型 |
| `content_angle` | 切り口 |
| `media_label` | メディアラベル |
| `text_length_bucket` | 文字数帯 |
| `analyzed_at` | 分析日時（ISO8601） |
