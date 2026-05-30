# メディア再利用リスクポリシー

**最終更新**: 2026-05-30

---

## 基本方針

`reference_posts` から収集したメディア（画像・動画）は、**参考閲覧目的のみ**を前提とする。

デフォルトの `reuse_status` は `reference_only`。明示的な承認なしに投稿への再利用は行わない。

---

## リスク判定基準（assess_imitation_risk）

`src/media/cloudinary_client.py` の `assess_imitation_risk()` で自動判定する。

| リスク | 判定条件 |
|---|---|
| `low` | 自アカウントのメディアURL（account_idと一致するドメイン等） |
| `medium` | パブリックなCDN（`pbs.twimg.com` 等）の画像 |
| `high` | 動画（`amplify_video` 等）、または判定根拠が乏しい場合 |
| `unknown` | URL が空または判定不能 |

---

## 実装上のルール

1. `reference_only` のメディアは投稿生成に**使用しない**。
2. `approved` のメディアのみ `used_count` を加算して投稿に使用する。
3. Cloudinaryへのアップロードは `ALLOW_CLOUDINARY_UPLOAD=true` かつ `dry_run=False` の場合のみ行う。
4. 実在アカウント由来の動画は `media_reuse_risk=high` として記録する。
5. `rejected` のメディアは投稿処理パイプラインで除外する。

---

## 将来の拡張（Phase 4 以降）

- AIによる自動リスク判定（テキスト・画像認識）
- `approved` への自動エスカレーション（自社アカウントのメディアに限定）
- 使用回数制限（`used_count >= 3` で `review` へ格下げ）
