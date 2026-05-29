"""
publishers/x_publisher.py - X（旧 Twitter）Publisher（Phase 3-D）

本番投稿の有効化条件（すべて必要）:
  1. PUBLISH_ENABLED=true
  2. ALLOW_REAL_X_POST=true
  3. X OAuth 1.0a の認証情報4項目すべて設定済み
     (X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET)
  4. publish_queue.py で --confirm-real-post が指定されていること

文字数制限:
  X_CHAR_LIMIT = 140  (超過は FAIL)
  X_CHAR_WARN  = 120  (超過は WARN / success=True)

Threads 投稿は Phase 3-E で実装。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from publishers.base import BasePublisher, PublishResult
from publishers.dry_run import _check_x

X_CHAR_LIMIT = 140
X_CHAR_WARN = 120


class XPublisher(BasePublisher):
    """X（旧 Twitter）投稿 Publisher（Phase 3-D: tweepy OAuth 1.0a 実装）。"""

    platform: str = "x"

    def publish(
        self,
        text: str,
        *,
        account: dict,
        derivative: dict,
        queue_item: dict,
        dry_run: bool = True,
    ) -> PublishResult:
        account_id = account.get("account_id", "")
        queue_id = queue_item.get("queue_id", "")
        derivative_id = derivative.get("derivative_id", "")

        # ---- dry_run=True: DryRunPublisher 相当の検証のみ ----
        if dry_run:
            if not text.strip():
                return PublishResult(
                    platform="x",
                    success=False,
                    dry_run=True,
                    message=f"FAIL: テキストが空です (account={account_id} queue_id={queue_id})",
                )
            success, message = _check_x(text)
            if success:
                message += (
                    f" | account={account_id}"
                    f" derivative_id={derivative_id}"
                    f" queue_id={queue_id}"
                )
            return PublishResult(
                platform="x",
                success=success,
                dry_run=True,
                posted_url=None,
                external_post_id=None,
                message=message,
            )

        # ---- dry_run=False: 安全ガード 1: PUBLISH_ENABLED ----
        publish_enabled = os.environ.get("PUBLISH_ENABLED", "false").strip().lower()
        if publish_enabled not in ("1", "true", "yes"):
            return PublishResult(
                platform="x",
                success=False,
                dry_run=False,
                message=(
                    "SAFETY_STOP: PUBLISH_ENABLED=false です。"
                    " X への本番投稿には PUBLISH_ENABLED=true が必要です。"
                    f" (queue_id={queue_id})"
                ),
            )

        # ---- 安全ガード 2: ALLOW_REAL_X_POST ----
        allow_real = os.environ.get("ALLOW_REAL_X_POST", "false").strip().lower()
        if allow_real not in ("1", "true", "yes"):
            return PublishResult(
                platform="x",
                success=False,
                dry_run=False,
                message=(
                    "SAFETY_STOP: ALLOW_REAL_X_POST=false です。"
                    " Phase 3-D の手動テスト時のみ true にしてください。"
                    f" (queue_id={queue_id})"
                ),
            )

        # ---- テキスト検証 ----
        if not text.strip():
            return PublishResult(
                platform="x",
                success=False,
                dry_run=False,
                message=f"FAIL: テキストが空です (account={account_id} queue_id={queue_id})",
            )

        char_count = len(text)
        if char_count > X_CHAR_LIMIT:
            return PublishResult(
                platform="x",
                success=False,
                dry_run=False,
                message=(
                    f"FAIL: X投稿が {char_count}字でX制限({X_CHAR_LIMIT}字)を超えています"
                    f" (queue_id={queue_id})"
                ),
            )

        # ---- 認証情報チェック ----
        from config_loader import get_x_credentials
        creds = get_x_credentials()
        missing = [
            k for k, v in [
                ("X_API_KEY", creds.get("api_key")),
                ("X_API_SECRET", creds.get("api_secret")),
                ("X_ACCESS_TOKEN", creds.get("access_token")),
                ("X_ACCESS_TOKEN_SECRET", creds.get("access_token_secret")),
            ] if not v
        ]
        if missing:
            return PublishResult(
                platform="x",
                success=False,
                dry_run=False,
                message=(
                    f"SAFETY_STOP: X API 認証情報が未設定です: {missing}"
                    f" (queue_id={queue_id})"
                    " .env に X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET を設定してください"
                ),
            )

        # ---- 本番投稿 ----
        return self._publish_with_oauth1(
            text=text,
            creds=creds,
            account_id=account_id,
            queue_id=queue_id,
            derivative_id=derivative_id,
        )

    def _publish_with_oauth1(
        self,
        text: str,
        creds: dict,
        account_id: str,
        queue_id: str,
        derivative_id: str,
    ) -> PublishResult:
        """tweepy OAuth 1.0a で X に投稿する。"""
        try:
            import tweepy
        except ImportError:
            return PublishResult(
                platform="x",
                success=False,
                dry_run=False,
                message=(
                    "FAIL: tweepy がインストールされていません。"
                    " `pip install tweepy>=4.14.0` を実行してください。"
                    f" (queue_id={queue_id})"
                ),
            )

        try:
            client = tweepy.Client(
                consumer_key=creds["api_key"],
                consumer_secret=creds["api_secret"],
                access_token=creds["access_token"],
                access_token_secret=creds["access_token_secret"],
            )
            response = client.create_tweet(text=text)
            tweet_id = str(response.data["id"])
            posted_url = self._build_posted_url(tweet_id)
            posted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            return PublishResult(
                platform="x",
                success=True,
                dry_run=False,
                posted_url=posted_url,
                external_post_id=tweet_id,
                message=(
                    f"OK: X投稿成功 tweet_id={tweet_id}"
                    f" | account={account_id}"
                    f" queue_id={queue_id}"
                    f" derivative_id={derivative_id}"
                    f" posted_at={posted_at}"
                ),
            )
        except Exception as e:
            return PublishResult(
                platform="x",
                success=False,
                dry_run=False,
                posted_url=None,
                external_post_id=None,
                message=(
                    f"POST_FAILED: X投稿に失敗しました: {type(e).__name__}: {e}"
                    f" (queue_id={queue_id} account={account_id})"
                ),
            )

    def _build_posted_url(self, tweet_id: str) -> str:
        return f"https://twitter.com/i/web/status/{tweet_id}"
