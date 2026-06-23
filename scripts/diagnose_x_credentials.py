#!/usr/bin/env python3
"""diagnose_x_credentials.py — X API credentials 診断（投稿しない）

調査項目:
1. credentials 4項目の SET/MISSING 確認（値は表示しない）
2. GET /2/users/me で認証が通るか（read 権限テスト）
3. レスポンス status code の分類
4. 402/401/403/429 の分類
5. 旧repo方式（requests_oauthlib.OAuth1）でのテスト
"""
from __future__ import annotations
import os, sys, json

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except ImportError:
    pass

import requests
from requests_oauthlib import OAuth1

X_API_KEY        = os.environ.get("X_API_KEY", "").strip()
X_API_SECRET     = os.environ.get("X_API_SECRET", "").strip()
X_ACCESS_TOKEN   = os.environ.get("X_ACCESS_TOKEN", "").strip()
X_ACCESS_TOKEN_SECRET = os.environ.get("X_ACCESS_TOKEN_SECRET", "").strip()

USERS_ME_URL = "https://api.twitter.com/2/users/me"
TWEET_URL    = "https://api.twitter.com/2/tweets"


def mask(val: str) -> str:
    if not val:
        return "MISSING"
    return f"SET (len={len(val)})"


def classify_status(code: int) -> str:
    return {
        200: "OK",
        401: "UNAUTHORIZED (認証情報が無効)",
        402: "PAYMENT_REQUIRED (課金または権限問題)",
        403: "FORBIDDEN (アプリの Read/Write 設定を確認)",
        429: "RATE_LIMIT (レート制限)",
    }.get(code, f"UNKNOWN_{code}")


def main():
    print("=== X API Credential Diagnostic ===")
    print()

    # 1. credential SET/MISSING
    print("[1] Credentials チェック（値は非表示）")
    creds_ok = True
    for name, val in [
        ("X_API_KEY", X_API_KEY),
        ("X_API_SECRET", X_API_SECRET),
        ("X_ACCESS_TOKEN", X_ACCESS_TOKEN),
        ("X_ACCESS_TOKEN_SECRET", X_ACCESS_TOKEN_SECRET),
    ]:
        status = mask(val)
        ok = bool(val)
        if not ok:
            creds_ok = False
        print(f"  {'✅' if ok else '❌'} {name}: {status}")

    if not creds_ok:
        print("\n[FAIL] credentials が不足しています。.env を確認してください。")
        return 1

    print("\n[2] 投稿方式: requests_oauthlib.OAuth1 (HMAC-SHA1) — 旧repo X_autopost_yoru と同一方式")

    auth = OAuth1(
        client_key=X_API_KEY,
        client_secret=X_API_SECRET,
        resource_owner_key=X_ACCESS_TOKEN,
        resource_owner_secret=X_ACCESS_TOKEN_SECRET,
        signature_method="HMAC-SHA1",
    )

    # 2. GET /2/users/me — read test（投稿なし）
    print("\n[3] GET /2/users/me — 認証テスト（投稿なし）")
    try:
        resp = requests.get(USERS_ME_URL, auth=auth, timeout=15)
        code = resp.status_code
        classification = classify_status(code)
        print(f"  HTTP {code}: {classification}")

        if code == 200:
            data = resp.json().get("data", {})
            uid = data.get("id", "?")
            username = data.get("username", "?")
            print(f"  user_id={uid}  username=@{username}")
            print(f"  → 認証OK / read権限あり")
            print(f"  → 投稿可能性: {'高 (write権限も通常セット)' if code == 200 else '要確認'}")
        elif code == 401:
            print(f"  → 認証失敗。credentials の値が間違っている可能性。")
            print(f"  → response: {resp.text[:300]}")
        elif code == 402:
            print(f"  → 402: read endpoint でも 402 が出ています。")
            print(f"  → likely_cause: wrong_project_or_app / actual_billing_blocker")
            print(f"  → response: {resp.text[:300]}")
        elif code == 403:
            print(f"  → 403: アプリの権限設定を確認してください。")
            print(f"  → response: {resp.text[:300]}")
        elif code == 429:
            reset = resp.headers.get("x-rate-limit-reset", "?")
            print(f"  → レート制限。reset={reset}")
        else:
            print(f"  → 予期しないレスポンス: {resp.text[:300]}")

    except Exception as e:
        print(f"  → リクエスト失敗: {e}")

    # 3. 投稿方式の比較サマリー
    print("\n[4] 調査サマリー")
    print("  旧repo X_autopost_yoru:")
    print("    - 投稿方式: requests_oauthlib.OAuth1 + requests.post(json=...)")
    print("    - tweepy: 未使用")
    print("    - 最終成功: 2026-06-19")
    print("  新repo sns-growth-engine (修正前):")
    print("    - 投稿方式: tweepy.Client.create_tweet()")
    print("    - 最終失敗: 402 POST_FAILED_EXTERNAL_BILLING_BLOCKER")
    print("  新repo sns-growth-engine (修正後):")
    print("    - 投稿方式: requests_oauthlib.OAuth1 (旧repoと同一)")
    print("    - tweepy: 使用しない")

    print("\n[5] 投稿テスト方法 (診断完了後、必要なら実行)")
    print("  PUBLISH_ENABLED=true ALLOW_REAL_X_POST=true \\")
    print("  python3 scripts/publish_x_post.py \\")
    print("    --account-id night_scout \\")
    print("    --text '投稿テキスト' \\")
    print("    --confirm-post --no-dry-run")

    return 0


if __name__ == "__main__":
    sys.exit(main())
