"""
tone_checker.py - アカウント別NGトーンパターン判定

seeds.py の ACCOUNT_NG_TONE_PATTERNS を使って投稿テキストを検査する。
生成後の後処理チェックとして使用する。

Usage:
    from tone_checker import check_ng_tone
    result = check_ng_tone("投稿テキスト", "night_scout")
    if result.status == "FAIL":
        print(f"NGパターン検出: {result.matched_patterns}")
"""
from __future__ import annotations

from dataclasses import dataclass, field

from seeds import ACCOUNT_NG_TONE_PATTERNS


@dataclass
class ToneCheckResult:
    status: str                      # OK / FAIL
    account_id: str
    matched_patterns: list[str] = field(default_factory=list)
    message: str = ""


def check_ng_tone(text: str, account_id: str) -> ToneCheckResult:
    """テキストにアカウント別NGトーンパターンが含まれていないか確認する。

    一致パターンが1件でもあれば FAIL を返す。
    """
    patterns = ACCOUNT_NG_TONE_PATTERNS.get(account_id, [])
    matched = [p for p in patterns if p in text]

    if not matched:
        return ToneCheckResult(
            status="OK",
            account_id=account_id,
            matched_patterns=[],
            message="NGトーンパターン不検出",
        )

    return ToneCheckResult(
        status="FAIL",
        account_id=account_id,
        matched_patterns=matched,
        message=f"NGトーンパターン検出: {matched}",
    )
