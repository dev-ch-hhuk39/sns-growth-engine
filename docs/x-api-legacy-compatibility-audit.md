# X API Legacy Compatibility Audit

- 作成日: 2026-06-24
- 担当: Claude Code (Sonnet 4.6)
- 調査対象: 旧repo `X_autopost_yoru` vs 新repo `sns-growth-engine` の X 投稿方式差分

## 調査背景

新repo で X 投稿時に `402 CreditsDepleted` が発生。旧repo は 2026-06-19 まで正常投稿していた。  
「課金不足」ではなく「クレジット枯渇（月次 API Credits）」であることを確認するため、  
新旧 repo の実装差分を徹底調査した。

## 新旧 repo 比較

| 項目 | 旧repo (X_autopost_yoru) | 新repo (sns-growth-engine) 修正前 | 新repo (sns-growth-engine) 修正後 |
|---|---|---|---|
| ライブラリ | `requests_oauthlib.OAuth1` | `tweepy.Client` | `requests_oauthlib.OAuth1` |
| 認証方式 | HMAC-SHA1 | Bearer Token + OAuth1 混在 | HMAC-SHA1 |
| エンドポイント | `https://api.twitter.com/2/tweets` | `https://api.twitter.com/2/tweets` | `https://api.twitter.com/2/tweets` |
| 402 分類 | なし（エラーハンドリングなし） | `POST_FAILED_EXTERNAL_BILLING_BLOCKER` | `POST_FAILED_X_402_CREDITS_DEPLETED` |
| 最終投稿成功日 | 2026-06-19 | — | 未確認（クレジット枯渇中） |

## 結論

**tweepy.Client による 402 ではない。X API Credits の月次枯渇が原因。**

- 旧repo の高頻度 API 呼び出し（collect/analyze/generate）で月次クレジットを消費しきった
- tweepy.Client が 402 を出していたのは `requests` レイヤーが同じ状況に当たっていたから
- 認証方式を `requests_oauthlib.OAuth1` に戻しても 402 は継続 → クレジット枯渇確定
- X Developer Portal > Usage & Credits でクレジット残量を確認・補充すれば投稿再開可能

## 修正内容 (src/publishers/x_publisher.py)

- `_publish_with_oauth1()` を `tweepy.Client` から `requests_oauthlib.OAuth1` に変更
- `TWEET_URL = "https://api.twitter.com/2/tweets"` 定数を追加
- `_handle_post_error()` を追加：402/CreditsDepleted / 401 / 403 / 429 を個別分類

```python
TWEET_URL = "https://api.twitter.com/2/tweets"

def _publish_with_oauth1(self, text, creds, account_id, queue_id, derivative_id):
    import requests
    from requests_oauthlib import OAuth1
    auth = OAuth1(
        client_key=creds["api_key"],
        client_secret=creds["api_secret"],
        resource_owner_key=creds["access_token"],
        resource_owner_secret=creds["access_token_secret"],
        signature_method="HMAC-SHA1",
    )
    response = requests.post(TWEET_URL, auth=auth, json={"text": text}, timeout=30)
    if response.status_code >= 400:
        return self._handle_post_error(...)
    tweet_id = str(response.json()["data"]["id"])
    ...
```

## エラーコード定義

| コード | HTTP | 条件 |
|---|---|---|
| `POST_FAILED_X_402_CREDITS_DEPLETED` | 402 | body に `CreditsDepleted` を含む |
| `POST_FAILED_X_402_NEEDS_INVESTIGATION` | 402 | body に `CreditsDepleted` を含まない |
| `POST_FAILED_X_401_UNAUTHORIZED` | 401 | 認証失敗 |
| `POST_FAILED_X_403_FORBIDDEN` | 403 | 権限なし |
| `POST_FAILED_X_429_RATE_LIMIT` | 429 | レート制限 |

## 診断コマンド

```bash
# credentials 確認（投稿なし）
python3 scripts/diagnose_x_credentials.py

# dry-run 確認
python3 scripts/publish_x_post.py --account-id night_scout \
  --text 'テスト文' --confirm-post --dry-run
```

## 復旧手順

1. X Developer Portal (<https://developer.twitter.com/en/portal/dashboard>) にアクセス
2. "Usage & Credits" でクレジット残量確認
3. クレジット補充 or 月次リセット待ち
4. `diagnose_x_credentials.py` で credentials 再確認
5. dry-run → 実投稿

## 関連ファイル

- `src/publishers/x_publisher.py`
- `scripts/diagnose_x_credentials.py`
- `scripts/test_x_legacy_compatibility.py`
- `docs/x-api-billing-blocker.md`
