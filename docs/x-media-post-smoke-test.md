# X メディア付き投稿 Smoke Test 手順

## 概要

X（旧Twitter）へのメディア付き投稿のためのpreflight手順。
このドキュメントの手順は**実投稿直前のチェック**であり、実行には追加の明示的なフラグが必要。

## 前提条件

以下が全て揃っていること:

- [ ] X API認証情報 4項目が設定済み
- [ ] Cloudinary にメディアアップロード済み
- [ ] `media_assets` タブに `storage_url` が記録済み
- [ ] 投稿テキスト 120文字以内
- [ ] `rights_review_required=false`
- [ ] `media_reuse_risk != high`
- [ ] queue.status=READY の候補が存在
- [ ] posted_results に同一コンテンツが存在しない

## 1. X API 認証情報の設定項目

```env
X_API_KEY=your_api_key
X_API_SECRET=your_api_secret
X_ACCESS_TOKEN=your_access_token
X_ACCESS_TOKEN_SECRET=your_access_token_secret
PUBLISH_ENABLED=false      # 投稿直前のみ true
ALLOW_REAL_X_POST=false    # 投稿直前のみ true
```

## 2. メディア付き投稿の確認項目

```bash
# preflight チェック（実投稿なし・常時安全）
python scripts/preflight_x_real_post.py --account-id night_scout

# キュー確認
python scripts/review_queue.py --account-id night_scout --status READY
```

確認項目:
- `media_asset_id`: media_assetsタブのID
- `storage_url`: Cloudinary の URL（`https://res.cloudinary.com/...`）
- `media_type`: `image` または `video`
- `cloudinary_uploaded`: `true`

## 3. テキストのみ 1件投稿コマンド

**実投稿には以下が全て必要:**
- PUBLISH_ENABLED=true（手動で設定）
- ALLOW_REAL_X_POST=true（手動で設定）
- --confirm-real-post フラグ
- --queue-id での1件指定
- --max-real-posts 1

```bash
# 実投稿コマンド（今は実行しない）
python scripts/publish_queue.py \
  --account-id night_scout \
  --queue-id {queue_id} \
  --confirm-real-post \
  --max-real-posts 1
```

## 4. メディア付き1件投稿コマンド

```bash
# メディア付き実投稿コマンド（今は実行しない）
python scripts/publish_queue.py \
  --account-id night_scout \
  --queue-id {queue_id} \
  --with-media \
  --confirm-real-post \
  --max-real-posts 1
```

## 5. 投稿後の false 戻し

実投稿後は**必ず**以下を実施する:

```bash
python -c "
import re, pathlib
env = pathlib.Path('.env').read_text()
env = re.sub(r'PUBLISH_ENABLED=true', 'PUBLISH_ENABLED=false', env)
env = re.sub(r'ALLOW_REAL_X_POST=true', 'ALLOW_REAL_X_POST=false', env)
pathlib.Path('.env').write_text(env)
print('安全フラグをfalseに戻しました')
"
```

## 6. posted_results 確認

```bash
python scripts/check_pipeline_integrity.py --account-id night_scout
```

投稿後の記録確認:
- `result_id`: 自動採番
- `post_id`: X が返すpost ID
- `posted_at`: 投稿日時
- `status`: POSTED

## 7. queue.status 確認

投稿後は queue.status が `DONE` または `POSTED` になっていること:

```bash
python scripts/review_queue.py --account-id night_scout --status DONE
```

## 8. 失敗時の戻し方

```bash
# queue.status を READY に戻す
python scripts/review_queue.py \
  --queue-id {queue_id} \
  --set-status WAITING_REVIEW \
  --account-id night_scout

# 安全フラグを false に戻す
python -c "
import re, pathlib
env = pathlib.Path('.env').read_text()
env = re.sub(r'PUBLISH_ENABLED=true', 'PUBLISH_ENABLED=false', env)
env = re.sub(r'ALLOW_REAL_X_POST=true', 'ALLOW_REAL_X_POST=false', env)
pathlib.Path('.env').write_text(env)
"
```

## 9. 誤投稿防止チェックリスト

実投稿前の最終確認:

- [ ] テスト環境ではなく本番アカウントか確認
- [ ] 投稿テキストに個人情報・機密情報が含まれていないか
- [ ] メディアの著作権問題がないか（rights_review_required=false）
- [ ] 同一コンテンツの重複投稿でないか
- [ ] --max-real-posts 1 で1件のみ指定しているか
- [ ] 投稿後の false 戻し手順を把握しているか

## 関連ファイル

- `scripts/preflight_x_real_post.py` - 投稿前チェック
- `scripts/publish_queue.py` - 投稿実行
- `scripts/review_queue.py` - キュー確認
- `docs/x-real-post-final-checklist.md` - 最終チェックリスト
- `docs/queue-status-lifecycle.md` - ステータス管理
