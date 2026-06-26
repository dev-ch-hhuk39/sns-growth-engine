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

## 未実装（意図的に保留 / 別途ユーザー判断）

- queue 行への media 添付（`attach_media_to_queue.py`）
- ThreadsPublisher の media 投稿配線（dry-run 限定で配線予定。実 media 投稿は禁止のまま）
- Cloudinary 実 upload（`ALLOW_CLOUDINARY_UPLOAD=true` 明示時のみ）
