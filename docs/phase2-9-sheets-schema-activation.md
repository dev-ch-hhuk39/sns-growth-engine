# Phase 2.9: Sheets スキーマ有効化

**実施日**: 2026-05-30

---

## 実施内容

`setup_and_verify.py --setup --verify` を実行し、実スプレッドシートに Phase 2.8 で定義した3タブを追加した。

### 追加タブ

| タブ名 | 用途 |
|---|---|
| `media_assets` | Cloudinary保存メディアを一元管理（Phase 2.12 で本格利用） |
| `reference_post_scores` | 参考投稿のパフォーマンス分析結果（Phase 2.11 で書き込み） |
| `generation_jobs` | 8:2投稿生成計画の設定（Phase 2.13 で本格利用） |

### reference_posts 追加列

Phase 2.10 X reference collector 移植に合わせて以下6列を追加した（冪等追加、既存データへの影響なし）。

| 追加列 | 用途 |
|---|---|
| `original_text` | 元投稿の生テキスト（text は要約・整形後） |
| `account_handle` | @ハンドル名（author は表示名） |
| `reply_count` | 返信数 |
| `bookmark_count` | 保存数（Xブックマーク） |
| `collected_at` | 収集日時（ISO8601） |
| `keywords` | 収集元キーワード（`\|` 区切り） |

### 既存タブへの影響

- 既存データは一切削除・変更していない
- 既存列の並び順は変更していない（冪等設計）
- accounts / drafts / social_derivatives / queue / logs は変更なし

---

## 実行コマンド

```bash
# dry-run で確認
python scripts/setup_and_verify.py --dry-run

# 実行
python scripts/setup_and_verify.py --setup --verify
```

---

## 次のフェーズ

- Phase 2.10: X reference collector の本格移植
- Phase 2.11: reference_post_analyzer でスコアを reference_post_scores に書き込む
