# X API Billing Blocker — POST_FAILED_EXTERNAL_BILLING_BLOCKER

## 概要

- 発生日: 2026-06-22
- エラー: `402 Payment Required`
- 分類: `POST_FAILED_EXTERNAL_BILLING_BLOCKER`（外部課金ブロッカー）

## これは何か

X API の無料枠（Free tier）では投稿 API (`POST /2/tweets`) が使えません。  
OAuth 1.0a 認証は成功しており、**コードや認証情報の問題ではありません**。

| 項目 | 状態 |
|---|---|
| OAuth 認証 | **成功**（account ID: 1974127896232091648） |
| 投稿失敗原因 | X API クレジット不足（課金プラン未契約） |
| credentials error | **No** |
| コードの問題 | **No** |
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
| `POST_FAILED_EXTERNAL_BILLING_BLOCKER` | X API 402 — 外部課金ブロッカー。認証は成功。再試行可能 |
| `POST_FAILED` | その他の投稿失敗（認証エラー、ネットワーク等） |
| `SAFETY_STOP` | 安全ガードによる停止（PUBLISH_ENABLED 未設定等） |

## 関連ファイル

- `src/publishers/x_publisher.py` — 402 検出 + manual_queue 保存ロジック
- `data/manual_post_queue.json` — 失敗投稿の退避先（git管理外）
- `docs/first-live-post-report.md` — 初回パイロット実行レポート
