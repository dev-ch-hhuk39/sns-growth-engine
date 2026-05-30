# Phase 2.11: reference_post_analyzer 移植

**実施日**: 2026-05-30

---

## 概要

`X_autopost_yoru/x_analyze_posts.py` の分析ロジックを v2 に移植した。

pandas を使わない pure Python 実装。JSON/mock 入力 / dry-run で動作確認可能な状態まで実装。

---

## 実装ファイル

| ファイル | 役割 |
|---|---|
| `src/analyzers/reference_post_analyzer.py` | スコアリング・分類・パーセンタイル計算 |
| `scripts/analyze_references.py` | 分析 CLI |
| `fixtures/sample_x_posts.json` | 6件のテスト用ダミーデータ（3件追加） |
| `scripts/test_phase211.py` | Phase 2.11 テスト（117 PASS） |

---

## 実装した関数

| 関数 | 説明 |
|---|---|
| `to_int(value)` | None/空/int/float/str を int に安全変換 |
| `to_bool(value)` | TRUE/1/YES → True |
| `detect_content_angle(text)` | 体験談/ノウハウ/暴露/共感/質問/その他 |
| `detect_hook_style(text)` | リスト型/質問型/暴露型/体験談型/断定型/不明 |
| `text_length_bucket(length)` | 短文/中短文/中文/長文 の4区分 |
| `media_label_from_post(post)` | 動画あり/画像あり/メディアなし（media_urls 文字列から判定） |
| `calculate_performance_score(post)` | スコア計算式を適用 |
| `calculate_buzz_score(perf, thresholds)` | min(100.0, perf/500×100) |
| `_percentile_rank(values, value)` | pandas rank(pct=True, method='average') 相当 |
| `why_it_grew(post, analysis, thresholds)` | バズ理由を読点区切りで生成 |
| `replay_tip(post, analysis)` | 再現ポイントを「/」区切りで生成 |
| `analyze_reference_post(post, ...)` | 1件分析（percentile は 0.0 プレースホルダー） |
| `analyze_reference_posts(posts, ...)` | バッチ分析（percentile をバッチ更新） |

---

## スコア計算式

```
performance_score = likes + reposts×3 + reply_count×2 + bookmark_count×4 + impressions/100
buzz_score        = min(100.0, performance_score / 500 × 100)
```

### DEFAULT_THRESHOLDS

| キー | 値 | 説明 |
|---|---|---|
| `buzz_like_count` | 100 | why_it_grew のいいね閾値 |
| `buzz_impression_count` | 10000 | why_it_grew のインプレッション閾値 |
| `performance_score_per_100_buzz` | 500 | buzz_score = 100 になる performance_score |
| `relative_top_cutoff` | 0.8 | 上位20% パーセンタイルカットオフ |

---

## パーセンタイル計算（2パス方式）

1. `analyze_reference_post()`: `account_percentile = 0.0` のプレースホルダーで返す
2. `analyze_reference_posts()`: 全件スコア計算後、グループ内でパーセンタイルをバッチ更新
   - `account_percentile`: `account_id` ごとにグループ化
   - `keyword_percentile`: `keywords`（パイプ区切り）ごとにグループ化（空は「キーワードなし」）
3. パーセンタイル確定後に `why_it_grew` / `replay_tip` を再計算

---

## media_label の判定ロジック

`media_urls`（パイプ区切り文字列）を検査する。

1. `.mp4` / `.mov` / `amplify_video` が含まれる → `動画あり`
2. 空でない → `画像あり`
3. 空 / None → `メディアなし`

---

## v2 カラム名マッピング（旧 x_analyze_posts.py との対応）

| 旧 (x_analyze_posts.py) | v2 reference_posts |
|---|---|
| `like_count` | `likes` |
| `repost_count` | `reposts` |
| `impression_count` | `impressions` |
| `reply_count` | `reply_count`（同じ） |
| `bookmark_count` | `bookmark_count`（同じ） |
| `hook_text` | `extracted_hook` |

---

## analyze_references.py の使い方

```bash
# JSONフィクスチャ → dry-run（Sheetsへ書かない）
python scripts/analyze_references.py \
  --account-id night_scout \
  --input-json fixtures/sample_x_posts.json \
  --raw-json \
  --dry-run

# Sheetsから reference_posts を読んで分析（dry-run）
python scripts/analyze_references.py \
  --account-id night_scout \
  --use-sheets \
  --dry-run

# 実Sheets → reference_post_scores に保存
python scripts/analyze_references.py \
  --account-id night_scout \
  --use-sheets --test-write
```

### 安全フラグ

| フラグ | 説明 |
|---|---|
| `--dry-run` | Sheetsへの書き込みをスキップ（デフォルト ON） |
| `--use-sheets` | 実SheetsClient を使用 |
| `--test-write` | 実Sheetsへ書き込みを実行（--use-sheetsと組み合わせる） |
| `--raw-json` | `--input-json` が raw X 形式のとき、正規化を通す |

---

## SheetsClient に追加したメソッド

| メソッド | 説明 |
|---|---|
| `get_reference_post_scores(account_id, reference_post_id, limit)` | スコアタブから取得 |
| `find_reference_post_score_by_reference_post_id(reference_post_id)` | 1件引き当て |
| `save_reference_post_score(score)` | reference_post_id でアップサート |
| `save_reference_post_scores(scores)` | バッチ保存、`{"saved": n, "skipped": n, "errors": n}` を返す |

MockSheetsClient にも同じメソッドを追加済み。

---

## 次のフェーズ

- Phase 2.12: `cloudinary_client.py` で media_assets に保存する
- Phase 2.13: `generation_planner.py` で 8:2 生成計画を generation_jobs に書き込む
