"""
publishers/factory.py - Publisher ファクトリ

get_publisher(platform, dry_run) で適切な Publisher を返す。

Phase 3-D（現在）:
  - dry_run=True  → 全プラットフォームで DryRunPublisher を返す
  - dry_run=False + platform="x" → XPublisher を返す
    ※ XPublisher 内の安全ガード（PUBLISH_ENABLED / ALLOW_REAL_X_POST / 認証情報）が
       すべて通過した場合のみ本番投稿を実行する
  - dry_run=False + その他 → _SafetyStopPublisher（安全停止）

Phase 3-E で切り替え予定（Threads）:
  - dry_run=False かつ platform="threads" → ThreadsPublisher を返す
  - 以下のコメントを外す

フェーズ移行メモ:
  Phase 3-D: XPublisher 有効化済み
  Phase 3-E: ThreadsPublisher のコメントを外す
"""
from __future__ import annotations

from .base import BasePublisher, PublishResult
from .dry_run import DryRunPublisher

SUPPORTED_PLATFORMS = {"x", "threads", "note"}


def get_publisher(platform: str, dry_run: bool = True) -> BasePublisher:
    """platform と dry_run フラグに基づいて Publisher を返す。

    Args:
        platform: "x" / "threads" / "note" 等
        dry_run: True = DryRunPublisher（実投稿しない）
                 False = 本番 Publisher（安全ガードは各 Publisher が担う）

    Returns:
        BasePublisher のインスタンス
    """
    plat = platform.lower()

    if dry_run:
        return DryRunPublisher()

    # Phase 3-D: XPublisher が安全ガードを担う
    if plat == "x":
        from .x_publisher import XPublisher
        return XPublisher()

    # Phase 3-E でコメントを外す:
    # elif plat == "threads":
    #     from publishers.threads_publisher import ThreadsPublisher
    #     return ThreadsPublisher()

    return _SafetyStopPublisher(platform=plat)


class _SafetyStopPublisher(BasePublisher):
    """Phase 3-C の安全停止用 Publisher。

    dry_run=False が要求されても本番投稿せず SAFETY_STOP を返す。
    factory.py が本番 Publisher を返す前の安全ネット。
    """

    def __init__(self, platform: str = "unknown") -> None:
        self._platform = platform

    @property
    def platform(self) -> str:  # type: ignore[override]
        return self._platform

    def publish(
        self,
        text: str,
        *,
        account: dict,
        derivative: dict,
        queue_item: dict,
        dry_run: bool = True,
    ) -> PublishResult:
        queue_id = queue_item.get("queue_id", "?")
        account_id = account.get("account_id", "?")
        return PublishResult(
            platform=self._platform,
            success=False,
            dry_run=False,
            posted_url=None,
            external_post_id=None,
            message=(
                f"SAFETY_STOP: factory.py は Phase 3-C では本番 Publisher を返しません。"
                f" platform={self._platform!r} queue_id={queue_id} account={account_id}"
                f" → Phase 3-D 以降に factory.py の XPublisher コメントを外してください。"
            ),
        )
