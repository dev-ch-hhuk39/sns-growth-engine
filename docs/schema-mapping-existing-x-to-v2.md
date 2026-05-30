# スキーマ対応表: 既存X（6タブ） ↔ v2（12+3タブ）

**作成日**: 2026-05-29

---

## 全体対応表

| 既存タブ（feature/x-analysis-pipeline） | v2 タブ | 対応方針 |
|---|---|---|
| `98_収集内部`（RAW_HEADERS 47列） | `reference_posts`（既存） | RAW → reference_posts へマッピング |
| `01_収集投稿`（COLLECTION_HEADERS 39列） | `reference_post_scores`（新規追加） | 分析結果をスコアタブへ |
| `02_承認レビュー`（REVIEW_HEADERS 25列） | `social_derivatives` + `queue` | 承認済み → WAITING_REVIEW |
| `03_投稿キュー`（QUEUE_HEADERS 18列） | `queue`（既存） | status を v2 語彙に統一 |
| `00_ダッシュボード`（DASHBOARD_HEADERS 5列） | `category_scores`（既存） | Phase 4 相当 |
| `99_システム`（SYSTEM_HEADERS 3列） | `logs`（既存） | key/value → logs へ |
| —（未実装） | `media_assets`（新規追加） | Cloudinary 保存 |
| —（未実装） | `generation_jobs`（新規追加） | 8:2 生成計画 |

---

## カラム詳細マッピング

### 98_収集内部（RAW_HEADERS） → reference_posts

| 既存カラム（RAW） | v2 reference_posts カラム | 備考 |
|---|---|---|
| `post_id` | `post_id` | 同一 |
| `post_url` | `post_url` | 同一 |
| `platform` | `platform` | 同一 |
| `account_name` | `author` | |
| `account_id` | `account_id` | v2ではnight_scout/liver_manager |
| `posted_at` | `published_at` | |
| `text` | `text` | 同一 |
| `hook_text` | `extracted_hook` | |
| `image_urls` | `media_urls` | `|` 区切り → そのまま |
| `video_urls` | `media_urls`（末尾に追記） | |
| `like_count` | `likes` | |
| `repost_count` | `reposts` | |
| `impression_count` | `impressions` | |
| `imitation_risk` | `imitation_risk` | 新規追加カラム |
| `source_type` | `source_type` | account_monitor / keyword_search |

---

### 01_収集投稿（COLLECTION_HEADERS） → reference_post_scores（新規タブ）

| 既存カラム | v2 reference_post_scores カラム | 備考 |
|---|---|---|
| `投稿ID` | `reference_post_id` | |
| `いいね数` | `like_score` | |
| `リポスト数` | `repost_score` | |
| `返信数` | `reply_score` | |
| `保存数` | `bookmark_score` | |
| `インプレッション数` | `impression_score` | |
| —（計算値） | `performance_score` | like + repost×3 + reply×2 + bookmark×4 + impression/100 |
| `バズ判定` | `buzz_score` | 0 or 1 → 将来数値化 |
| `アカウント内上位20%` | `account_percentile` | 0.0〜1.0 |
| `キーワード群内上位20%` | `keyword_percentile` | 0.0〜1.0 |
| `切り口` | `content_angle` | |
| `書き出し型` | `hook_style` | |
| `伸びた理由` | `why_it_grew` | |
| `再現ポイント` | `replay_tip` | |
| `文字数` | `text_length_bucket` | 短文/中短文/中文/長文 |
| `画像あり` | `media_label` | 画像あり/動画あり/なし |

---

### 02_承認レビュー（REVIEW_HEADERS） → social_derivatives + queue

| 既存カラム | v2 対応 | 備考 |
|---|---|---|
| `投稿ID` | `social_derivatives.derivative_id` の参照元 | |
| `リライト案A` | `social_derivatives.text`（採用案A選択時） | |
| `リライト案B` | `social_derivatives.text`（採用案B選択時） | |
| `採用案` | `social_derivatives.status = READY` 条件 | A/B → READY昇格 |
| `転載可否` | `social_derivatives.reason` | 転載OK → READY |
| `投稿可否` | `social_derivatives.status` 条件 | 投稿OK → READY |
| `X投稿するか` | `queue.platform = x` | |
| `Threads投稿するか` | `queue.platform = threads` | |
| `確認メモ` | `queue.error` or `notes` | |

---

### 03_投稿キュー（QUEUE_HEADERS） → queue（v2既存タブ）

| 既存カラム | v2 queue カラム | 備考 |
|---|---|---|
| `キューID` | `queue_id` | 形式変更: `x-{source_id}` → UUID |
| `元投稿ID` | `draft_id` | reference_post_id への参照 |
| `投稿文` | `social_derivatives.text`（参照） | queue タブには保持しない設計 |
| `X投稿状態` | `status` | 投稿待ち → READY, 投稿済み → POSTED |
| `X投稿日時` | `processed_at` | |
| `最終更新日時` | — | logs タブで代替 |

---

### ステータス語彙の統一

| 既存（日本語） | v2（英語） |
|---|---|
| 投稿待ち | WAITING_REVIEW または READY |
| 投稿済み | POSTED |
| スキップ | — （queue から除外） |
| エラー | READY（error カラムに詳細） |

---

## v2 新規追加タブ（Phase 2.8で追加）

### media_assets（新規）

既存に相当タブなし。`保存メディアURL` / `保存メディアパス` が `02_承認レビュー` に存在したが、専用タブとして分離する。

→ Cloudinary アップロード結果・reuse_status・imitation_risk を管理。

### reference_post_scores（新規）

既存の `01_収集投稿` に相当するが、v2 設計では分析スコアを独立タブに分離する。

→ performance_score / hook_style / content_angle / buzz_score 等を管理。

### generation_jobs（新規）

既存に相当タブなし。8:2 投稿比率の計画・設定を管理する新規タブ。

→ account_id / platform / reference_based_ratio / daily_target_count 等を管理。

---

## 設計判断: v2 12タブ維持

既存6タブをそのまま採用するのではなく、**v2 の12タブ設計を維持した上で3タブを追加**する。

理由:
- v2 の queue / social_derivatives / drafts / accounts 構造が既に実装・テスト済み
- 既存6タブの日本語スキーマを英語 v2 スキーマに変換する移植コストより、
  新タブ追加の方がリスクが低い
- 将来の Threads / note 拡張も v2 設計の方が対応しやすい
