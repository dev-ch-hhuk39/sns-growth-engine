# end_to_end_publish_preflight

X / Threads で単発・ツリー・動画付き投稿を1件ずつ安全に確認する統合 preflight（Phase 7.D）。

## 概要

- platform: x / threads
- post_type: single_post / thread_series / media_post / video_clip_post
- 実投稿なし・secret 表示なし
- draft_only / inactive アカウントは BLOCKED
- 安全フラグ（PUBLISH_ENABLED / ALLOW_REAL_*_POST）を確認

## チェック一覧

| # | チェック項目 |
|---|------------|
| 1 | アカウントステータス（active / draft_only / inactive） |
| 2 | PUBLISH_ENABLED / ALLOW_REAL_*_POST フラグ確認 |
| 3 | プラットフォーム対応確認 |
| 4 | post_type 別チェック（文字数・series_id・media_asset） |
| 5 | posted_results 重複確認 |

## 結果ステータス

| status | 意味 |
|--------|------|
| READY | 実投稿可能条件が揃っている |
| WARN | 要確認事項あり（実投稿は可能だが確認推奨） |
| NOT_READY | FAIL がある（実投稿禁止） |
| BLOCKED | draft_only / inactive アカウント（実投稿絶対禁止） |

## 使い方

```bash
# night_scout / X / single_post
python scripts/preflight_end_to_end_publish.py --account-id night_scout --platform x --post-type single_post --mock

# night_scout / Threads / thread_series
python scripts/preflight_end_to_end_publish.py --account-id night_scout --platform threads --post-type thread_series --series-id ts_night_scout_threads_xxx --mock

# beauty_account（→ BLOCKED）
python scripts/preflight_end_to_end_publish.py --account-id beauty_account --platform x --post-type single_post --mock
```

## 安全ルール

- beauty_account は全 post_type / 全 platform で BLOCKED
- inactive アカウントも BLOCKED
- PUBLISH_ENABLED=false を常に維持
- ALLOW_REAL_X_POST=false / ALLOW_REAL_THREADS_POST=false を常に維持
- Cloudinary upload 未完了 media は BLOCKED
- rights_review_required=true は BLOCKED
- media_reuse_risk=high は BLOCKED
