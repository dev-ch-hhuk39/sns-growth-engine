# content_mix_planner

単発投稿 / ツリー投稿 / 参考投稿 / 動画参考投稿をアカウントごとの比率で自動選択する（Phase 7.A）。

## 概要

- アカウントID・プラットフォームごとに投稿種別の比率を持つ
- random seed指定で再現可能
- dry-run default（実投稿なし・READY/POSTED なし）
- beauty_account は draft_only → 全アイテム `WAITING_REVIEW`
- active アカウントは `PLANNED`

## content_type 一覧

| type | 説明 |
|------|------|
| single_post | 単発投稿 |
| thread_series | ツリー投稿 |
| reference_based | 参考投稿ベース |
| video_clip_reference | 動画クリップ参考 |
| original_hypothesis | オリジナル仮説 |

## 初期比率設定（config/content_mix/default_mix.json）

| アカウント | single | thread | reference | video |
|-----------|--------|--------|-----------|-------|
| night_scout (x) | 40 | 30 | 20 | 10 |
| liver_manager (x) | 35 | 35 | 20 | 10 |
| beauty_account (x) | 40 | 40 | 20 | 0 |

## 使い方

```bash
# dry-run（デフォルト）
python scripts/plan_content_mix.py --account-id night_scout --platform x --count 10 --seed 42 --dry-run

# beauty_account（WAITING_REVIEW のみ）
python scripts/plan_content_mix.py --account-id beauty_account --platform x --count 5 --dry-run

# force_mode（全件同一種別）
python scripts/plan_content_mix.py --account-id night_scout --platform x --count 5 --force-mode thread_series
```

## 安全ルール

- 実投稿なし
- READY / POSTED 化なし
- beauty_account は常に WAITING_REVIEW
- inactive アカウントは生成対象外
