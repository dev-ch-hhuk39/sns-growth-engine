#!/usr/bin/env python3
"""test_x_legacy_compatibility.py — X Publisher が旧repo互換方式を使うことを確認する。

旧repo X_autopost_yoru は requests_oauthlib.OAuth1 (HMAC-SHA1) で直接 POST /2/tweets。
tweepy.Client は 402 CreditsDepleted が出るため使用しない。
"""
from __future__ import annotations
import sys, os, inspect

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT); sys.path.insert(0, os.path.join(_ROOT, "src"))

PASS = FAIL = 0

def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  [PASS] {label}")
    else:
        FAIL += 1; print(f"  [FAIL] {label}")

print("=== test_x_legacy_compatibility ===")

# 1. x_publisher.py が tweepy.Client を使っていないことを確認
src_path = os.path.join(_ROOT, "src", "publishers", "x_publisher.py")
src = open(src_path).read()
check("tweepy.Client を使っていない", "tweepy.Client(" not in src)
check("tweepy.create_tweet を使っていない", "client.create_tweet(" not in src)
check("requests_oauthlib.OAuth1 を使っている", "OAuth1(" in src)
check("HMAC-SHA1 を使っている", "HMAC-SHA1" in src)
check("TWEET_URL = https://api.twitter.com/2/tweets", "https://api.twitter.com/2/tweets" in src)

# 2. _handle_post_error が 402/CreditsDepleted を正しく分類するか
sys.path.insert(0, os.path.join(_ROOT, "src"))
from publishers.x_publisher import XPublisher
pub = XPublisher()

# 402 CreditsDepleted → POST_FAILED_X_402_CREDITS_DEPLETED
result = pub._handle_post_error(
    status_code=402,
    response_text='{"title":"CreditsDepleted","detail":"no credits"}',
    text="test", account_id="night_scout", queue_id="test_q"
)
check("402 CreditsDepleted → POST_FAILED_X_402_CREDITS_DEPLETED", "CREDITS_DEPLETED" in result.message)

# 402 一般 → POST_FAILED_X_402_NEEDS_INVESTIGATION
result2 = pub._handle_post_error(
    status_code=402,
    response_text='{"error":"payment required"}',
    text="test", account_id="night_scout", queue_id="test_q"
)
check("402 一般 → NEEDS_INVESTIGATION", "NEEDS_INVESTIGATION" in result2.message)

# 401 → UNAUTHORIZED
result3 = pub._handle_post_error(
    status_code=401, response_text='{"error":"unauthorized"}',
    text="test", account_id="night_scout", queue_id="test_q"
)
check("401 → POST_FAILED_X_401_UNAUTHORIZED", "401_UNAUTHORIZED" in result3.message)

# 403 → FORBIDDEN
result4 = pub._handle_post_error(
    status_code=403, response_text='{"error":"forbidden"}',
    text="test", account_id="night_scout", queue_id="test_q"
)
check("403 → POST_FAILED_X_403_FORBIDDEN", "403_FORBIDDEN" in result4.message)

# 429 → RATE_LIMIT
result5 = pub._handle_post_error(
    status_code=429, response_text='{"error":"rate limit"}',
    text="test", account_id="night_scout", queue_id="test_q"
)
check("429 → POST_FAILED_X_429_RATE_LIMIT", "429_RATE_LIMIT" in result5.message)

# 3. diagnose_x_credentials.py が存在する
check("diagnose_x_credentials.py が存在する",
      os.path.exists(os.path.join(_ROOT, "scripts", "diagnose_x_credentials.py")))

# 4. _publish_with_oauth1 が requests_oauthlib を import する
src_method = ""
for name, method in inspect.getmembers(XPublisher, predicate=inspect.isfunction):
    if name == "_publish_with_oauth1":
        src_method = inspect.getsource(method)
check("_publish_with_oauth1 が requests_oauthlib.OAuth1 を使う", "from requests_oauthlib import OAuth1" in src_method)
check("_publish_with_oauth1 が tweepy を使わない", "import tweepy" not in src_method)

print(f"\n結果: PASS={PASS} FAIL={FAIL} / {PASS+FAIL}件")
sys.exit(0 if FAIL == 0 else 1)
