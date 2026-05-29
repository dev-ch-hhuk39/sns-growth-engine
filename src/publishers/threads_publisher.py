"""
publishers/threads_publisher.py - Threads Publisher スタブ（Phase 3-C）

現時点（Phase 3-C）では本番 POST を行わない安全スタブ。
dry_run=True の場合は DryRunPublisher 相当の検証を実施する。
dry_run=False かつ安全ガード通過後も、現時点では NotImplementedError で停止する。

本番投稿の有効化条件（Phase 3-E 以降）:
  1. PUBLISH_ENABLED=true
  2. ALLOW_REAL_THREADS_POST=true
  3. THREADS_ACCESS_TOKEN / THREADS_USER_ID が設定済み
  4. Threads API v1.0 の投稿実装が完了

投稿フォーマット推奨:
  - 1行目: フック（読み手を引き込む一文）
  - 2行目: 空行
  - 3行目以降: 本文
  Threads は空行なしでも投稿できるが、視認性のため推奨
"""
from __future__ import annotations

import os

from publishers.base import BasePublisher, PublishResult
from publishers.dry_run import _check_threads


class ThreadsPublisher(BasePublisher):
    """Threads 投稿 Publisher（Phase 3-C: スタブ実装）。

    Phase 3-C では本番 POST を行わない。
    Phase 3-E で Threads API v1.0 を使った実投稿を実装する。
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

        # ---- dry_run=True: DryRunPublisher 相当の検証のみ ----
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
                    "SAFETY_STOP: PUBLISH_ENABLED=false です。"
                    " Threads への本番投稿は Phase 3-E まで実施しません。"
                    f" (queue_id={queue_id})"
                ),
            )

        if allow_real not in ("1", "true", "yes"):
            return PublishResult(
                platform="threads",
                success=False,
                dry_run=False,
                message=(
                    "SAFETY_STOP: ALLOW_REAL_THREADS_POST=false です。"
                    " Phase 3-E の手動テスト時のみ true にしてください。"
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

        # ---- Phase 3-E まで本番実装しない ----
        raise NotImplementedError(
            "ThreadsPublisher の本番投稿は Phase 3-E で実装します。"
            " 現時点（Phase 3-C）では本番 POST を行いません。"
            f" queue_id={queue_id} account={account_id}"
        )
