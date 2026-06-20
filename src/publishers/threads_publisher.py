"""
publishers/threads_publisher.py - Threads Publisher（Phase 3-E）

Threads Graph API v1.0 を使った実投稿実装。
2ステップ: コンテナ作成 → 公開。

安全ガード:
  - PUBLISH_ENABLED=true が必要
  - ALLOW_REAL_THREADS_POST=true が必要
  - トークンは data/threads_tokens/{account_id}.json または環境変数から取得
  - dry_run=True では API 呼び出しなし

投稿フォーマット推奨:
  - 1行目: フック（読み手を引き込む一文）
  - 2行目: 空行
  - 3行目以降: 本文
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .base import BasePublisher, PublishResult
from .dry_run import _check_threads

THREADS_API_BASE = "https://graph.threads.net/v1.0"
_DEFAULT_TOKEN_DIR = Path(os.environ.get("THREADS_TOKEN_STORE_DIR", "data/threads_tokens"))
JST = timezone(timedelta(hours=9))


def _get_credentials(account_id: str) -> tuple[str, str]:
    """(access_token, user_id) を取得する。値はログに出さない。

    優先順位:
    1. data/threads_tokens/{account_id}.json の access_token
    2. THREADS_ACCESS_TOKEN_{ACCOUNT_ID_UPPER} 環境変数
    3. THREADS_ACCESS_TOKEN 環境変数（後方互換）

    user_id:
    1. THREADS_USER_ID_{ACCOUNT_ID_UPPER} 環境変数
    2. THREADS_USER_ID 環境変数
    """
    token_path = _DEFAULT_TOKEN_DIR / f"{account_id}.json"
    access_token = ""
    if token_path.exists():
        try:
            with open(token_path) as f:
                stored = json.load(f)
            access_token = stored.get("access_token", "")
        except (json.JSONDecodeError, OSError):
            pass

    if not access_token:
        key = f"THREADS_ACCESS_TOKEN_{account_id.upper()}"
        access_token = os.environ.get(key, "").strip()
    if not access_token:
        access_token = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()

    user_id_key = f"THREADS_USER_ID_{account_id.upper()}"
    user_id = os.environ.get(user_id_key, "").strip()
    if not user_id:
        user_id = os.environ.get("THREADS_USER_ID", "").strip()

    return access_token, user_id


def _create_container(
    user_id: str,
    access_token: str,
    text: str,
    media_type: str = "TEXT",
) -> str:
    """投稿コンテナを作成し、container_id を返す。"""
    import requests

    url = f"{THREADS_API_BASE}/{user_id}/threads"
    payload: dict[str, Any] = {
        "media_type": media_type,
        "text": text,
        "access_token": access_token,
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    container_id = data.get("id")
    if not container_id:
        raise RuntimeError(f"コンテナ作成失敗: レスポンスに id がありません: {data}")
    return container_id


def _publish_container(
    user_id: str,
    access_token: str,
    container_id: str,
) -> dict:
    """コンテナを公開し、レスポンスを返す（post_id を含む）。"""
    import requests

    url = f"{THREADS_API_BASE}/{user_id}/threads_publish"
    payload = {
        "creation_id": container_id,
        "access_token": access_token,
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _build_post_url(user_id: str, post_id: str) -> str:
    return f"https://www.threads.net/@{user_id}/post/{post_id}"


class ThreadsPublisher(BasePublisher):
    """Threads 投稿 Publisher（Phase 3-E: 実投稿実装）。

    テキスト投稿のみ対応（メディア付きは Phase 4 以降）。
    """

    platform: str = "threads"

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

        # ---- dry_run=True: 検証のみ ----
        if dry_run:
            if not text.strip():
                return PublishResult(
                    platform="threads",
                    success=False,
                    dry_run=True,
                    message=f"FAIL: テキストが空です (account={account_id} queue_id={queue_id})",
                )
            success, message = _check_threads(text)
            if success:
                message += (
                    f" | account={account_id}"
                    f" derivative_id={derivative_id}"
                    f" queue_id={queue_id}"
                )
            return PublishResult(
                platform="threads",
                success=success,
                dry_run=True,
                posted_url=None,
                external_post_id=None,
                message=message,
            )

        # ---- dry_run=False: 安全ガードチェック ----
        publish_enabled = os.environ.get("PUBLISH_ENABLED", "false").strip().lower()
        allow_real = os.environ.get("ALLOW_REAL_THREADS_POST", "false").strip().lower()

        if publish_enabled not in ("1", "true", "yes"):
            return PublishResult(
                platform="threads",
                success=False,
                dry_run=False,
                message=(
                    "SAFETY_STOP: PUBLISH_ENABLED が false です。"
                    " .env に PUBLISH_ENABLED=true を設定してください。"
                    f" (queue_id={queue_id})"
                ),
            )

        if allow_real not in ("1", "true", "yes"):
            return PublishResult(
                platform="threads",
                success=False,
                dry_run=False,
                message=(
                    "SAFETY_STOP: ALLOW_REAL_THREADS_POST が false です。"
                    " 1件手動テスト時のみ .env に ALLOW_REAL_THREADS_POST=true を設定してください。"
                    f" (queue_id={queue_id})"
                ),
            )

        # ---- テキスト検証 ----
        if not text.strip():
            return PublishResult(
                platform="threads",
                success=False,
                dry_run=False,
                message=f"FAIL: テキストが空です (account={account_id} queue_id={queue_id})",
            )

        success, check_msg = _check_threads(text)
        if not success:
            return PublishResult(
                platform="threads",
                success=False,
                dry_run=False,
                message=f"FAIL: テキスト検証失敗: {check_msg} (queue_id={queue_id})",
            )

        # ---- 認証情報確認 ----
        access_token, user_id = _get_credentials(account_id)
        if not access_token:
            return PublishResult(
                platform="threads",
                success=False,
                dry_run=False,
                message=(
                    f"SAFETY_STOP: アカウント '{account_id}' の THREADS_ACCESS_TOKEN が未設定です。"
                    f" data/threads_tokens/{account_id}.json または"
                    f" THREADS_ACCESS_TOKEN_{account_id.upper()} を設定してください。"
                    f" (queue_id={queue_id})"
                ),
            )
        if not user_id:
            return PublishResult(
                platform="threads",
                success=False,
                dry_run=False,
                message=(
                    f"SAFETY_STOP: アカウント '{account_id}' の THREADS_USER_ID が未設定です。"
                    f" THREADS_USER_ID_{account_id.upper()} または THREADS_USER_ID を設定してください。"
                    f" (queue_id={queue_id})"
                ),
            )

        # ---- 実投稿: 2ステップ ----
        try:
            container_id = _create_container(user_id, access_token, text)
            time.sleep(1)  # Threads API 推奨: コンテナ作成後に少し待つ
            result = _publish_container(user_id, access_token, container_id)
        except Exception as e:
            return PublishResult(
                platform="threads",
                success=False,
                dry_run=False,
                message=f"FAIL: Threads API エラー: {e} (queue_id={queue_id})",
                raw_response=None,
            )

        post_id = result.get("id", "")
        posted_url = _build_post_url(user_id, post_id) if post_id else None

        return PublishResult(
            platform="threads",
            success=True,
            dry_run=False,
            posted_url=posted_url,
            external_post_id=post_id,
            message=(
                f"OK: Threads 投稿成功"
                f" post_id={post_id}"
                f" account={account_id}"
                f" queue_id={queue_id}"
            ),
            raw_response=result,
        )
