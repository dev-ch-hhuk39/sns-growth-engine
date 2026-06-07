# X本番投稿前 最終チェックリスト（Phase 3-E）

## 概要

X API を使った実投稿を行う前に必ず確認するチェックリスト。

**今回は実投稿しない。** 実行コマンドはこのドキュメントに記載するが実施しないこと。

## Preflight チェック実行

```bash
# モックで確認
python scripts/preflight_x_real_post.py --mock

# 実Sheets で確認
python scripts/preflight_x_real_post.py --account-id night_scout
```

## 必須チェック項目

| # | チェック内容 | 合格条件 |
|---|---|---|
| 1 | `X_API_KEY` | set（値非表示） |
| 2 | `X_API_SECRET` | set（値非表示） |
| 3 | `X_ACCESS_TOKEN` | set（値非表示） |
| 4 | `X_ACCESS_TOKEN_SECRET` | set（値非表示） |
| 5 | `PUBLISH_ENABLED` | `false` |
| 6 | `ALLOW_REAL_X_POST` | `false`（実投稿時のみ `true`） |
| 7 | tweepy | インストール済み |
| 8 | READY queue | 投稿候補あり |
| 9 | rights_review_required | `false`（`true` なら投稿不可） |
| 10 | media_reuse_risk | `low` or `medium`（`high` なら投稿不可） |
| 11 | 文字数 | 120文字以内（推奨） / 140文字以内（ハード） |
| 12 | media_asset | Cloudinary アップロード済み |

## 実投稿コマンド（今回は実行しない）

```bash
# 安全ガード解除（テスト完了後は必ず戻す）
PUBLISH_ENABLED=true ALLOW_REAL_X_POST=true \
  python scripts/publish_queue.py \
  --account-id night_scout \
  --platform x \
  --confirm-publish
```

## 投稿後の確認

1. X アカウントで投稿を確認
2. `posted_results` タブに記録されていることを確認
3. `PUBLISH_ENABLED=false` に戻す
4. `ALLOW_REAL_X_POST=false` に戻す

## 禁止事項

- `rights_review_required=true` の投稿
- `media_reuse_risk=high` の投稿
- 120文字超の投稿（推奨）
- 代理店・情報商材・副業系コンテンツ（night_scout / liver_manager 共通）
- テスト後の `PUBLISH_ENABLED=true` 放置

## .env 設定例

```
X_API_KEY=<your_api_key>
X_API_SECRET=<your_api_secret>
X_ACCESS_TOKEN=<your_access_token>
X_ACCESS_TOKEN_SECRET=<your_access_token_secret>
PUBLISH_ENABLED=false         # 通常は false
ALLOW_REAL_X_POST=false       # 通常は false
```
