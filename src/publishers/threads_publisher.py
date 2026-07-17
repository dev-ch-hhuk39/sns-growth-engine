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

import os
import time
from datetime import timedelta, timezone
from typing import Any

from .base import BasePublisher, PublishResult
from .dry_run import _check_threads
from .threads_credentials import resolve_credentials

THREADS_API_BASE = "https://graph.threads.net/v1.0"
JST = timezone(timedelta(hours=9))


def _get_credentials(account_id: str) -> tuple[str, str]:
    """(access_token, user_id) を取得する。値はログに出さない。"""
    creds = resolve_credentials(account_id)
    return creds["access_token"], creds["user_id"]


def _create_container(
    user_id: str,
    access_token: str,
    text: str,
    media_type: str = "TEXT",
    media_url: str | None = None,
) -> str:
    """投稿コンテナを作成し、container_id を返す。"""
    import requests

    url = f"{THREADS_API_BASE}/{user_id}/threads"
    payload: dict[str, Any] = {
        "media_type": media_type,
        "text": text,
        "access_token": access_token,
    }
    if media_url:
        payload["video_url" if media_type == "VIDEO" else "image_url"] = media_url
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    container_id = data.get("id")
    if not container_id:
        raise RuntimeError(f"コンテナ作成失敗: レスポンスに id がありません: {data}")
    return container_id


def _create_carousel_container(
    user_id: str,
    access_token: str,
    text: str,
    media_urls: list[str],
    media_types: list[str],
) -> str:
    """Create official Threads carousel children, then their parent container."""
    import requests

    children: list[str] = []
    for media_url, media_type in zip(media_urls, media_types):
        payload = {
            "media_type": media_type,
            "is_carousel_item": "true",
            "access_token": access_token,
            "video_url" if media_type == "VIDEO" else "image_url": media_url,
        }
        response = requests.post(f"{THREADS_API_BASE}/{user_id}/threads", data=payload, timeout=30)
        response.raise_for_status()
        child = str(response.json().get("id") or "")
        if not child:
            raise RuntimeError("Threads carousel child container missing id")
        if media_type == "VIDEO":
            _wait_for_video_container(child, access_token)
        children.append(child)
    response = requests.post(
        f"{THREADS_API_BASE}/{user_id}/threads",
        data={"media_type": "CAROUSEL", "text": text, "children": ",".join(children), "access_token": access_token},
        timeout=30,
    )
    response.raise_for_status()
    container_id = str(response.json().get("id") or "")
    if not container_id:
        raise RuntimeError("Threads carousel parent container missing id")
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


def _wait_for_video_container(container_id: str, access_token: str, *, attempts: int = 20) -> None:
    """Wait until Threads finishes ingesting a public video URL."""
    import requests

    url = f"{THREADS_API_BASE}/{container_id}"
    for _ in range(attempts):
        resp = requests.get(
            url,
            params={"fields": "status,error_message", "access_token": access_token},
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        status = str(payload.get("status") or "").upper()
        if status in {"FINISHED", "PUBLISHED"}:
            return
        if status in {"ERROR", "EXPIRED"}:
            raise RuntimeError("Threads video container processing failed")
        time.sleep(3)
    raise TimeoutError("Threads video container processing timed out")


def _try_fetch_permalink(post_id: str, access_token: str) -> str | None:
    """Threads API から投稿の permalink を取得する。失敗時は None を返す。

    数値 user_id をそのまま URL に使うと不正確（@username が必要）なため、
    API から permalink を取得するアプローチを採用。
    """
    try:
        import requests
        url = f"{THREADS_API_BASE}/{post_id}"
        params = {"fields": "permalink", "access_token": access_token}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        permalink = resp.json().get("permalink")
        return permalink if permalink else None
    except Exception:
        return None


class ThreadsPublisher(BasePublisher):
    """Threads text/video publisher with explicit media gates."""

    platform: str = "threads"

    def publish(
        self,
        text: str,
        *,
        account: dict,
        derivative: dict,
        queue_item: dict,
        dry_run: bool = True,
        media_url: str | None = None,
        media_type: str = "VIDEO",
        media_urls: list[str] | None = None,
        media_types: list[str] | None = None,
    ) -> PublishResult:
        account_id = account.get("account_id", "")
        queue_id = queue_item.get("queue_id", "")
        derivative_id = derivative.get("derivative_id", "")
        urls = [str(item).strip() for item in (media_urls or []) if str(item).strip()]
        types = [str(item).upper() for item in (media_types or [])]
        if not urls and media_url and media_url.strip():
            urls, types = [media_url.strip()], [media_type.upper()]
        if len(types) != len(urls):
            types = [media_type.upper()] * len(urls)
        has_media = bool(urls)
        carousel = len(urls) > 1
        mixed_carousel = carousel and len(set(types)) > 1

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
                if has_media:
                    message += f" | media_count={len(urls)} media_types={','.join(types)} (DRY_RUN_PLAN_ONLY)"
            return PublishResult(
                platform="threads",
                success=success,
                dry_run=True,
                posted_url=None,
                external_post_id=None,
                message=message,
            )

        # ---- dry_run=False: media は追加ゲートが必要 ----
        if has_media:
            allow_media = os.environ.get("ALLOW_MEDIA_POSTS", "false").strip().lower() in ("1", "true", "yes")
            allow_video = os.environ.get("ALLOW_REAL_THREADS_VIDEO_POST", "false").strip().lower() in ("1", "true", "yes")
            allow_carousel = os.environ.get("ALLOW_THREADS_CAROUSEL", "false").strip().lower() in ("1", "true", "yes")
            allow_mixed = os.environ.get("ALLOW_THREADS_MIXED_CAROUSEL", "false").strip().lower() in ("1", "true", "yes")
            if not allow_media or ("VIDEO" in types and not allow_video) or (carousel and not allow_carousel) or (mixed_carousel and not allow_mixed):
                return PublishResult(
                    platform="threads",
                    success=False,
                    dry_run=False,
                    message=(
                        "SAFETY_STOP: media投稿には media/video/carousel の明示gateが必要です。"
                        f" (account={account_id} queue_id={queue_id})"
                    ),
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
            if carousel:
                container_id = _create_carousel_container(user_id, access_token, text, urls, types)
            else:
                container_id = _create_container(user_id, access_token, text, media_type=types[0] if has_media else "TEXT", media_url=urls[0] if has_media else None)
            if has_media and not carousel and types[0] == "VIDEO":
                _wait_for_video_container(container_id, access_token)
            else:
                time.sleep(1)
            result = _publish_container(user_id, access_token, container_id)
        except Exception as exc:
            # requests exceptions may include a URL containing query credentials.
            # Never serialize the exception string into queue/log output.
            return PublishResult(
                platform="threads",
                success=False,
                dry_run=False,
                message=f"FAIL: Threads API エラー: {type(exc).__name__} (queue_id={queue_id})",
                raw_response=None,
            )

        post_id = result.get("id", "")
        posted_url = None
        permalink_pending = False
        if post_id:
            posted_url = _try_fetch_permalink(post_id, access_token)
            if posted_url is None:
                permalink_pending = True

        url_note = (
            f" posted_url={posted_url}"
            if posted_url
            else " permalink_pending=true (URLは API から取得できませんでした)"
        )

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
                f"{url_note}"
            ),
            raw_response=result,
        )
