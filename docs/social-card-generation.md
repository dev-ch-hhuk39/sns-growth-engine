# Self-Generated Social Card 生成

Date: 2026-06-26
Created: 2026-06-26

## 目的

Threads-first 運用の media パイプラインのうち、**法的リスクが最も低い「自前生成テキストカード」** を提供する。
第三者の画像/動画は一切扱わない。生成物は完全に自社著作物として扱える。

## 構成

- `src/media/social_card.py` — 描画ロジック（PIL）と self_generated レコード生成
- `scripts/generate_social_card.py` — 薄い CLI

## 安全設計

- フォーマット: `portrait` (1080x1350) / `square` (1080x1080)
- 生成物は `output/social_cards/` のみ（`.gitignore` 済み）。VPS / repo には保存しない。
- 既定は **dry-run 相当**: Sheets 書き込みなし、Cloudinary upload なし。
- 権利モデル（既存 `media_assets` 語彙に整合）:

  | フィールド | 値 | 意味 |
  |---|---|---|
  | `rights_policy` | `owned` | 自前生成なので所有 |
  | `reuse_policy` | `allow_reuse` | 再利用可（`no_reuse` ではない） |
  | `media_policy` | `owned` | `do_not_download` / `plan_only` ではない |
  | `status` | `SELF_GENERATED` | rights 上は投稿可 |
  | `source_id` | `self_generated` | レジストリ source に依存しない |

- **Cloudinary upload は権利が clear でも別ゲート**: `ALLOW_CLOUDINARY_UPLOAD=true` + `--confirm-upload` が無い限り
  `plan_cloudinary_upload` が `BLOCKED` を返す。本スクリプトは実 upload を行わない（plan 表示のみ）。

## 使い方

```bash
python3 scripts/generate_social_card.py \
    --account-id night_scout \
    --hook "深夜にこっそり読むやつ" \
    --body "今日の一歩は小さくていい。\n続けた人だけが、来月の自分に追い抜かれずに済む。" \
    --format portrait
```

`--body` の `\n` は改行に変換される。日本語はスペース無しで幅を測りながら文字単位で折り返す。
カードに収まらない本文は打ち切られる（カードは要約。全文は投稿テキスト側に残す）。

## テスト

```bash
python3 scripts/test_generate_social_card.py   # 22 PASS
```

検証内容: 両フォーマットのサイズ整合、不正フォーマット拒否、self_generated 権利値、
`no_reuse`/`plan_only` でないこと、Cloudinary ゲート維持、出力先が `output/` 配下であること。

## ThreadsPublisher の media 配線（dry-run 限定・実装済み）

`src/publishers/threads_publisher.py` の `publish()` に任意引数 `media_url` を追加した。

- **dry-run + media_url**: テキスト検証に加え「IMAGE 添付予定」を計画表示する（API 呼び出しなし）。
  メッセージ末尾に `media=IMAGE media_url=... (DRY_RUN_PLAN_ONLY)` が付く。
- **real mode + media_url**: `PUBLISH_ENABLED` / `ALLOW_REAL_THREADS_POST` が true でも
  env チェックより前に `SAFETY_STOP` で**ハードに拒否**する。実 media 投稿は構造的に不可能。
- **media_url なし**: 既存の text-only 挙動のまま（後方互換）。

テスト: `python3 scripts/test_threads_publisher_media_dryrun.py`（11 PASS）。
既存 publisher テスト（phase10 threads/x、phase13 safety、preflight）も回帰なし。

## queue への media 付与計画（plan-only・実装済み）

`src/media/queue_media_attach.py` + `scripts/attach_media_to_queue.py`。

- **計画のみ**。Sheets への書き込みは行わない（本番付与は別途ユーザー判断）。
- 付与候補にできるのは権利クリアな media だけ:
  - `status` ∈ {APPROVED, READY, SELF_GENERATED}
  - `rights_policy` ∈ {owned, allowed, approved}（unknown / not_allowed は不可）
  - `reuse_policy` ≠ no_reuse
  - `media_policy` ∉ {do_not_download, plan_only}
  - `media_reuse_risk` ≠ high
- URL 未確定（Cloudinary upload 前）の self_generated カードは `media_url_pending=true` として表示。
- 入力はオフライン JSON（`--input-json`）でレジストリ不要・credentials 不要・テスト可能。

テスト: `python3 scripts/test_attach_media_to_queue.py`（14 PASS）。

## 未実装（意図的に保留 / 別途ユーザー判断）

- queue worker (`process_threads_queue.py`) への media 読み込み配線
  （dry-run で media_url を publish() に渡す。本番 Sheets 読み込み 429 リスクを考慮し別途判断）
- queue 行への media_asset_id 実書き込み（本番 Sheets write）
- Cloudinary 実 upload（`ALLOW_CLOUDINARY_UPLOAD=true` 明示時のみ）
- 実 media 投稿（構造的に拒否中。本番化は別途レビュー必須）
