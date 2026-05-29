"""
publishers/dry_run.py - DryRunPublisher

実 SNS 投稿を一切行わず、投稿テキストの検証のみを行う Publisher。
publish_queue.py が Phase 3-A で使用するデフォルト Publisher。

検証内容:
  - テキストが空でないこと
  - X: 140字以内（120字超は WARN）
  - Threads: フック + 空行 + 本文の形式
"""
from __future__ import annotations

from publishers.base import BasePublisher, PublishResult

X_CHAR_LIMIT = 140
X_CHAR_WARN = 120


def _check_x(text: str) -> tuple[bool, str]:
    """X 投稿テキストを検証する。(success, message) を返す。"""
    length = len(text)
    if length == 0:
        return False, "FAIL: テキストが空です"
    if length > X_CHAR_LIMIT:
        return False, f"FAIL: X投稿が {length}字でX制限({X_CHAR_LIMIT}字)を超えています"
    if length > X_CHAR_WARN:
        return True, f"DRY_RUN: would post to X ({length}字) [WARN: 推奨上限({X_CHAR_WARN}字)超過]"
    return True, f"DRY_RUN: would post to X ({length}字)"


def _check_threads(text: str) -> tuple[bool, str]:
    """Threads 投稿テキストを検証する。(success, message) を返す。"""
    length = len(text)
    if length == 0:
        return False, "FAIL: テキストが空です"
    lines = text.split("\n")
    if len(lines) < 2:
        return True, f"DRY_RUN: would post to Threads ({length}字) [WARN: フック+本文の区切りなし（1行のみ）]"
    has_blank = any(line.strip() == "" for line in lines[1:3])
    if not has_blank:
        return True, f"DRY_RUN: would post to Threads ({length}字) [WARN: フックと本文の間に空行がない可能性あり]"
    return True, f"DRY_RUN: would post to Threads ({length}字)"


class DryRunPublisher(BasePublisher):
    """実 SNS 投稿を行わず、テキスト検証のみを行う Publisher。

    - posted_url は常に None
    - external_post_id は常に None
    - dry_run は常に True
    - Phase 3-A では全プラットフォームでこのクラスを使用する
    """

    platform: str = "dry_run"

    def publish(
        self,
        text: str,
        *,
        account: dict,
        derivative: dict,
        queue_item: dict,
        dry_run: bool = True,
    ) -> PublishResult:
        platform = str(
            derivative.get("platform") or queue_item.get("platform") or ""
        ).lower()
        account_id = account.get("account_id", "")
        derivative_id = derivative.get("derivative_id", "")
        queue_id = queue_item.get("queue_id", "")

        if not text.strip():
            return PublishResult(
                platform=platform,
                success=False,
                dry_run=True,
                message=f"FAIL: テキストが空です (account={account_id} queue_id={queue_id})",
            )

        if platform == "x":
            success, message = _check_x(text)
        elif platform == "threads":
            success, message = _check_threads(text)
        else:
            success = True
            message = f"DRY_RUN: would post to {platform or 'unknown'} ({len(text)}字)"

        if success:
            message += (
                f" | account={account_id}"
                f" derivative_id={derivative_id}"
                f" queue_id={queue_id}"
            )

        return PublishResult(
            platform=platform,
            success=success,
            dry_run=True,
            posted_url=None,
            external_post_id=None,
            message=message,
        )
