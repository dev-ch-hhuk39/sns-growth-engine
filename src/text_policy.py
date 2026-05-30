"""
text_policy.py — SNS投稿文字数ポリシー

プラットフォーム別の推奨上限・ハード上限を管理し、
入力テキストに対して OK / WARN / FAIL を判定する。

X:       推奨 120字 / ハード 140字
Threads: 推奨 600字 / ハード 800字
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


PolicyStatus = Literal["OK", "WARN", "FAIL"]


@dataclass(frozen=True)
class TextPolicyResult:
    status: PolicyStatus
    char_count: int
    message: str


_POLICIES: dict[str, dict[str, int]] = {
    "x": {"soft_limit": 120, "hard_limit": 140},
    "threads": {"soft_limit": 600, "hard_limit": 800},
}


def check_text_policy(text: str, platform: str) -> TextPolicyResult:
    """投稿テキストの文字数ポリシーを検証する。

    Args:
        text: 検証する投稿テキスト
        platform: "x" または "threads"

    Returns:
        TextPolicyResult(status, char_count, message)

    Raises:
        ValueError: platform が未知の場合
    """
    platform = platform.lower()
    if platform not in _POLICIES:
        raise ValueError(f"未知のプラットフォーム: {platform!r}. 対応: {list(_POLICIES)}")

    policy = _POLICIES[platform]
    soft = policy["soft_limit"]
    hard = policy["hard_limit"]
    count = len(text)

    if count <= soft:
        return TextPolicyResult(
            status="OK",
            char_count=count,
            message=f"OK ({count}/{soft}字)",
        )
    if count <= hard:
        return TextPolicyResult(
            status="WARN",
            char_count=count,
            message=f"推奨上限超過。リライト推奨 ({count}字 / 推奨{soft}字以内)",
        )
    return TextPolicyResult(
        status="FAIL",
        char_count=count,
        message=f"ハード上限超過。投稿不可 ({count}字 / 上限{hard}字)",
    )


def get_platform_limits(platform: str) -> dict[str, int]:
    """プラットフォームの文字数制限を返す。

    Returns: {"soft_limit": int, "hard_limit": int}
    """
    platform = platform.lower()
    if platform not in _POLICIES:
        raise ValueError(f"未知のプラットフォーム: {platform!r}")
    return dict(_POLICIES[platform])
