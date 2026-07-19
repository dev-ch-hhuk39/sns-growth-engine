"""
publishers/x_publisher.py - X（旧 Twitter）Publisher（Phase 3-D）

本番投稿の有効化条件（すべて必要）:
  1. PUBLISH_ENABLED=true
  2. ALLOW_REAL_X_POST=true
  3. X OAuth 1.0a の認証情報4項目すべて設定済み
     (X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET)
  4. publish_queue.py で --confirm-real-post が指定されていること

投稿方式:
  旧repo X_autopost_yoru と同一方式。
  requests + requests_oauthlib.OAuth1 (HMAC-SHA1) で直接 POST /2/tweets。
  tweepy.Client は 402 が出るため使用しない。
  旧repo で 2026-06-19 まで動作確認済み。

文字数制限:
  X_CHAR_LIMIT = 140  (超過は FAIL)
  X_CHAR_WARN  = 120  (超過は WARN / success=True)

Threads 投稿は Phase 3-E で実装。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from .base import BasePublisher, PublishResult
from .dry_run import _check_x

X_CHAR_LIMIT = 140
X_CHAR_WARN = 120
TWEET_URL = "https://api.twitter.com/2/tweets"


class XPublisher(BasePublisher):
    """X（旧 Twitter）投稿 Publisher（Phase 3-D: requests_oauthlib.OAuth1 直接方式）。

    旧repo X_autopost_yoru と同一の投稿方式 (2026-06-19 まで動作確認済み)。
    tweepy.Client は 402 が出るため使用しない。
    """

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

        # X publishing is outside the active production scope. Keep a third,
        # independent feature gate so credentials present in a local .env can
        # never turn this legacy path into a network call accidentally.
        x_publisher_enabled = os.environ.get("X_PUBLISHER_ENABLED", "false").strip().lower()
        if x_publisher_enabled not in ("1", "true", "yes"):
            return PublishResult(
                platform="x",
                success=False,
                dry_run=False,
                message=(
                    "SAFETY_STOP: X_PUBLISHER_ENABLED=false です。"
                    " 現在の本番運用はThreads専用です。"
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
        """requests_oauthlib.OAuth1 (HMAC-SHA1) で直接 POST /2/tweets する。

        旧repo X_autopost_yoru の auto_post.py と同一方式。
        tweepy.Client は 402 が出るため使用しない。
        """
        try:
            import requests
            from requests_oauthlib import OAuth1
        except ImportError:
            return PublishResult(
                platform="x",
                success=False,
                dry_run=False,
                message=(
                    "FAIL: requests または requests_oauthlib がインストールされていません。"
                    f" (queue_id={queue_id})"
                ),
            )

        try:
            auth = OAuth1(
                client_key=creds["api_key"],
                client_secret=creds["api_secret"],
                resource_owner_key=creds["access_token"],
                resource_owner_secret=creds["access_token_secret"],
                signature_method="HMAC-SHA1",
            )
            response = requests.post(
                TWEET_URL,
                auth=auth,
                json={"text": text},
                timeout=30,
            )

            if response.status_code >= 400:
                return self._handle_post_error(
                    status_code=response.status_code,
                    response_text=response.text,
                    text=text,
                    account_id=account_id,
                    queue_id=queue_id,
                )

            tweet_id = str(response.json()["data"]["id"])
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
                raw_response=response.json(),
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

    def _handle_post_error(
        self,
        status_code: int,
        response_text: str,
        text: str,
        account_id: str,
        queue_id: str,
    ) -> PublishResult:
        """HTTP エラーコードを分類して PublishResult を返す。"""
        if status_code == 401:
            reason = "POST_FAILED_X_401_UNAUTHORIZED: 認証情報が無効です。X_API_KEY / X_ACCESS_TOKEN を確認してください。"
        elif status_code == 403:
            reason = "POST_FAILED_X_403_FORBIDDEN: 権限がありません。X アプリの Read/Write 設定を確認してください。"
        elif status_code == 402:
            self._save_to_manual_queue(text=text, account_id=account_id, queue_id=queue_id)
            if "CreditsDepleted" in response_text:
                reason = (
                    "POST_FAILED_X_402_CREDITS_DEPLETED:"
                    " X API Credits が残高ゼロです (CreditsDepleted)。"
                    " X Developer Portal > Usage & Credits で残高確認。"
                    " 旧repo の多数 API 呼び出しで消費した可能性。月次リセットを待つか追加購入。"
                    " 投稿文は data/manual_post_queue.json に保存済み。"
                )
            else:
                reason = (
                    "POST_FAILED_X_402_NEEDS_INVESTIGATION:"
                    " X API 402 Payment Required。"
                    " likely_causes: credits_depleted / wrong_project_or_app / plan_mismatch。"
                    " X Developer Portal で Credits 残高を確認してください。"
                    " 投稿文は data/manual_post_queue.json に保存済み。"
                )
        elif status_code == 429:
            reason = "POST_FAILED_X_429_RATE_LIMIT: レート制限。しばらく待ってから再実行してください。"
        else:
            reason = f"POST_FAILED_X_{status_code}: 予期しないエラー。"

        return PublishResult(
            platform="x",
            success=False,
            dry_run=False,
            posted_url=None,
            external_post_id=None,
            message=(
                f"{reason}"
                f" HTTP={status_code}"
                f" response={response_text[:200]}"
                f" (queue_id={queue_id} account={account_id})"
            ),
        )

    def _is_billing_error(self, exc: Exception) -> bool:
        """後方互換: exception から 402 判定（現在は _handle_post_error で処理）。"""
        try:
            if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
                if exc.response.status_code == 402:
                    return True
        except Exception:
            pass
        return "402" in str(exc) or "Payment Required" in str(exc)

    def _save_to_manual_queue(
        self, text: str, account_id: str, queue_id: str
    ) -> None:
        """投稿失敗テキストを data/manual_post_queue.json に追記する。"""
        import json
        import pathlib

        queue_path = pathlib.Path(__file__).resolve().parents[2] / "data" / "manual_post_queue.json"
        queue_path.parent.mkdir(parents=True, exist_ok=True)

        if queue_path.exists():
            try:
                data = json.loads(queue_path.read_text(encoding="utf-8"))
            except Exception:
                data = {"queue": []}
        else:
            data = {"queue": []}

        attempted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = {
            "queue_id": queue_id,
            "account_id": account_id,
            "platform": "x",
            "text": text,
            "attempted_at": attempted_at,
            "failure_reason": "POST_FAILED_EXTERNAL_BILLING_BLOCKER",
            "status": "retry_ready",
            "retry_command": (
                f"PUBLISH_ENABLED=true ALLOW_REAL_X_POST=true "
                f"python3 scripts/publish_x_post.py "
                f"--account-id {account_id} "
                f"--text '<text_from_this_entry>' "
                f"--confirm-post --no-dry-run"
            ),
        }
        data["queue"].append(entry)
        queue_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _build_posted_url(self, tweet_id: str) -> str:
        return f"https://twitter.com/i/web/status/{tweet_id}"
