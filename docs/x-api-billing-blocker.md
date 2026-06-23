# X API Billing Blocker — CreditsDepleted (402)

## 概要

- 発生日: 2026-06-22 (初回) → 2026-06-24 (詳細調査)
- エラー: `402 Payment Required` + `{"title":"CreditsDepleted","detail":"Your enrolled account [...] does not have any credits to fulfill this request."}`
- 最新分類: `POST_FAILED_X_402_CREDITS_DEPLETED`（X API クレジット枯渇）
- 旧分類: `POST_FAILED_EXTERNAL_BILLING_BLOCKER`（誤分類 — 2026-06-24に修正）

## 原因の特定

`tweepy.Client.create_tweet()` 起因の問題ではなく、**X API Credits（月次クレジット）の枯渇**が真の原因。  
旧repo（X_autopost_yoru）は `requests_oauthlib.OAuth1` (HMAC-SHA1) を使い 2026-06-19 まで正常投稿していたが、  
collect/analyze/generate の高頻度 API 呼び出しで月次クレジットを消費しきった。

| 項目 | 状態 |
|---|---|
| OAuth 認証 | **成功**（account ID: 1974127896232091648） |
| 投稿失敗原因 | X API Credits 枯渇（CreditsDepleted） |
| tweepy 問題 | **修正済み** → requests_oauthlib.OAuth1 に変更 |
| credentials error | **No** |
| コードの問題 | **修正済み** |
| 二重投稿リスク | **No**（post_id 未払い出し） |

## 影響

- `posted_results` には記録しない（POSTED 扱いにしない）
- 投稿文は `data/manual_post_queue.json` に `status=retry_ready` で保存
- 再試行は X Developer Portal で課金プラン契約後に手動実行

## 復旧手順

### Step 1: X Developer Portal でプラン確認・契約

1. <https://developer.twitter.com/en/portal/dashboard> にアクセス
2. Basic Plan 以上に契約（月額 $100 / または無料枠の投稿 API 有効化を確認）
3. 同じ API KEY / ACCESS TOKEN のまま利用可能

### Step 2: manual_post_queue.json から投稿文を確認

```bash
cat data/manual_post_queue.json | python3 -m json.tool
```

### Step 3: dry-run で最終確認

```bash
python3 scripts/publish_x_post.py \
  --account-id night_scout \
  --text '指名が取れるキャバ嬢は、見た目だけじゃなく「また会いたい」と思わせる接客のプロ。相手を気持ちよくさせる「聞き方」と「返し」の積み重ねが、稼げる子の秘密なんだよね。' \
  --confirm-post --dry-run
```

### Step 4: 実投稿

```bash
PUBLISH_ENABLED=true ALLOW_REAL_X_POST=true \
python3 scripts/publish_x_post.py \
  --account-id night_scout \
  --text '指名が取れるキャバ嬢は、見た目だけじゃなく「また会いたい」と思わせる接客のプロ。相手を気持ちよくさせる「聞き方」と「返し」の積み重ねが、稼げる子の秘密なんだよね。' \
  --confirm-post --no-dry-run
```

### Step 5: 成功後 posted_results 登録

```bash
python3 scripts/import_posted_results.py \
  --account-id night_scout \
  --platform x \
  --post-id <tweet_id> \
  --post-url <tweet_url>
```

## エラーコード定義

| コード | 意味 |
|---|---|
| `POST_FAILED_X_402_CREDITS_DEPLETED` | X API 402 + CreditsDepleted — 月次クレジット枯渇。認証は成功。クレジット補充後に再試行可能 |
| `POST_FAILED_X_402_NEEDS_INVESTIGATION` | X API 402 + CreditsDepleted 以外 — 原因調査が必要 |
| `POST_FAILED_X_401_UNAUTHORIZED` | 認証失敗 — credentials を確認 |
| `POST_FAILED_X_403_FORBIDDEN` | 権限なし — account/app設定を確認 |
| `POST_FAILED_X_429_RATE_LIMIT` | レート制限 — 15分待機後に再試行 |
| `POST_FAILED` | その他の投稿失敗 |
| `SAFETY_STOP` | 安全ガードによる停止（PUBLISH_ENABLED 未設定等） |

## X API Legacy 互換方式 (2026-06-24 更新)

旧repo互換の `requests_oauthlib.OAuth1` (HMAC-SHA1) 方式に移行済み。  
`tweepy.Client.create_tweet()` は 402 CreditsDepleted を誤分類するため廃止。  
詳細は `docs/x-api-legacy-compatibility-audit.md` 参照。

## 関連ファイル

- `src/publishers/x_publisher.py` — 402 検出 + manual_queue 保存ロジック
- `data/manual_post_queue.json` — 失敗投稿の退避先（git管理外）
- `docs/first-live-post-report.md` — 初回パイロット実行レポート
