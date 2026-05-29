"""
publishers/base.py - Publisher 共通インターフェース

すべてのプラットフォーム向け Publisher はこのインターフェースを実装する。
dry_run=True がデフォルト。本番投稿系は Phase 3-B 以降に実装する。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PublishResult:
    """投稿処理の結果を表す値オブジェクト。"""
    platform: str
    success: bool
    dry_run: bool
    posted_url: str | None = None
    external_post_id: str | None = None
    message: str = ""
    raw_response: dict | None = None

    def is_dry_run_ok(self) -> bool:
        """dry-run 成功かどうかを返す。"""
        return self.dry_run and self.success

    def summary(self) -> str:
        """ログ出力用の一行サマリー。"""
        tag = "DRY_RUN" if self.dry_run else "REAL"
        result = "OK" if self.success else "FAIL"
        return f"[{tag}/{result}] {self.platform}: {self.message}"


class BasePublisher:
    """SNS 投稿 Publisher の抽象基底クラス。

    各プラットフォーム向け Publisher はこのクラスを継承し、
    publish() を実装する。

    dry_run=True のとき:
      - 実 SNS API は呼ばない
      - PublishResult(dry_run=True, posted_url=None, external_post_id=None) を返す

    dry_run=False のとき（Phase 3-B 以降に実装予定）:
      - 実 SNS API を呼ぶ
      - PUBLISH_ENABLED=true かつ認証情報が揃っていることを呼び出し元が保証する
    """

    platform: str = ""

    def publish(
        self,
        text: str,
        *,
        account: dict,
        derivative: dict,
        queue_item: dict,
        dry_run: bool = True,
    ) -> PublishResult:
        """投稿を実行する（または dry_run で検証する）。

        Args:
            text: 投稿テキスト
            account: accounts タブの行データ（account_id, cta_text 等）
            derivative: social_derivatives タブの行データ
            queue_item: queue タブの行データ
            dry_run: True = 検証のみ（実 SNS 投稿しない）
        Returns:
            PublishResult
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}.publish() が実装されていません"
        )
