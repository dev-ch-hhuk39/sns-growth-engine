"""
check_beauty_activation_readiness.py - beauty_account活性化条件チェック（Phase 8.H）

beauty_accountをactive化する前提条件を確認する。
現時点では必ずBLOCKED/NOT_READY。active化は行わない。

使い方:
  python scripts/check_beauty_activation_readiness.py --mock
  python scripts/check_beauty_activation_readiness.py --account-id beauty_account --mock

禁止事項:
  - beauty_accountのactive化
  - beauty_accountのREADY化
  - beauty_accountの実投稿
  - draft_only解除
  - allow_real_post=trueへの変更
"""
from __future__ import annotations

import argparse
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

RESULTS: list[tuple[str, str, str]] = []
PASS_COUNT = 0
FAIL_COUNT = 0
WARN_COUNT = 0
BLOCKED_COUNT = 0
NOT_READY_COUNT = 0

REQUIRED_THREAD_SERIES_COUNT = 10
REQUIRED_HUMAN_REVIEW_COUNT = 10
CONTENT_QUALITY_THRESHOLD = 7.0


def _add(level: str, label: str, msg: str) -> None:
    global PASS_COUNT, FAIL_COUNT, WARN_COUNT, BLOCKED_COUNT, NOT_READY_COUNT
    RESULTS.append((level, label, msg))
    icons = {
        "PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]",
        "BLOCKED": "[BLOCKED]", "NOT_READY": "[NOT_READY]", "INFO": "[INFO]",
    }
    icon = icons.get(level, f"[{level}]")
    print(f"  {icon} {label}: {msg}")
    if level == "PASS":
        PASS_COUNT += 1
    elif level == "FAIL":
        FAIL_COUNT += 1
    elif level == "WARN":
        WARN_COUNT += 1
    elif level == "BLOCKED":
        BLOCKED_COUNT += 1
    elif level == "NOT_READY":
        NOT_READY_COUNT += 1


def check_draft_only_status(account_id: str) -> None:
    print(f"\n[1] draft_only確認: {account_id}")
    _add("BLOCKED", "draft_only", f"{account_id} はdraft_only。active化はユーザー明示承認が必要。")
    _add("INFO", "policy", "draft_only解除 = このCLIでは行いません。ユーザーが明示的に指示した場合のみ。")


def check_thread_series_count(mock: bool = False) -> None:
    print(f"\n[2] thread_series生成数確認 (必要: {REQUIRED_THREAD_SERIES_COUNT}件以上)")
    if mock:
        current_count = 0
        _add(
            "NOT_READY", "thread_series_count",
            f"現在 {current_count} 件 (必要: {REQUIRED_THREAD_SERIES_COUNT}件以上) — NOT_READY",
        )
    else:
        _add("WARN", "thread_series_count", "実Sheetsへの接続なしでは確認不可 (--use-sheetsが必要)")


def check_human_review_count(mock: bool = False) -> None:
    print(f"\n[3] human review済み数確認 (必要: {REQUIRED_HUMAN_REVIEW_COUNT}件以上)")
    if mock:
        current_count = 0
        _add(
            "NOT_READY", "human_review_count",
            f"現在 {current_count} 件 (必要: {REQUIRED_HUMAN_REVIEW_COUNT}件以上) — NOT_READY",
        )
    else:
        _add("WARN", "human_review_count", "実Sheetsへの接続なしでは確認不可")


def check_medical_risk() -> None:
    print("\n[4] medical/ad risk確認")
    _add(
        "NOT_READY", "medical_ad_risk",
        "medical/ad risk = low が必要。human reviewなしでは判定不可。NOT_READY。",
    )
    _add("INFO", "before_after", "before/after断定禁止。価格/施術/クリニック断定禁止。")
    _add("INFO", "cta_check", "CTA過多禁止。")


def check_forbidden_keywords() -> None:
    print("\n[5] forbidden_keywords確認")
    try:
        from text_policy import load_text_policy
        policy = load_text_policy()
        keywords = policy.get("forbidden_keywords", [])
        beauty_keywords = [k for k in keywords if any(
            w in str(k).lower() for w in ["美容", "医療", "クリニック", "施術", "before", "after", "治療"]
        )]
        _add("PASS", "text_policy_loaded", f"forbidden_keywords: {len(keywords)}件")
        if beauty_keywords:
            _add("WARN", "beauty_keywords", f"美容系禁止キーワード候補: {len(beauty_keywords)}件 — 生成前に確認必要")
        else:
            _add("WARN", "beauty_keywords", "美容系禁止キーワードが未定義。追加を推奨。")
    except Exception as e:
        _add("WARN", "text_policy", f"text_policyロード不可: {e}")


def check_allow_real_post() -> None:
    print("\n[6] allow_real_post確認")
    allow = os.environ.get("ALLOW_REAL_X_POST", "false").lower()
    allow_t = os.environ.get("ALLOW_REAL_THREADS_POST", "false").lower()
    if allow == "true" or allow_t == "true":
        _add("WARN", "allow_real_post", "ALLOW_REAL_*_POST=true が設定されています — beauty_accountには適用しないでください")
    else:
        _add("PASS", "allow_real_post", "false（安全）— allow_real_post=trueへの変更は別途ユーザー承認が必要")


def print_activation_checklist() -> None:
    print("\n" + "="*60)
    print("  beauty_account 活性化チェックリスト (将来用)")
    print("="*60)
    checklist = [
        f"[ ] thread_series生成 {REQUIRED_THREAD_SERIES_COUNT}件以上",
        f"[ ] human review {REQUIRED_HUMAN_REVIEW_COUNT}件以上",
        "[ ] medical/ad risk = low (全件確認済み)",
        "[ ] forbidden_keywords なし",
        "[ ] before/after断定 なし",
        "[ ] 価格/施術/クリニック断定 なし",
        "[ ] CTA過多 なし",
        f"[ ] content quality score >= {CONTENT_QUALITY_THRESHOLD}",
        "[ ] draft_only解除 — ユーザー明示承認",
        "[ ] allow_real_post=true — 別途ユーザー承認",
    ]
    for item in checklist:
        print(f"  {item}")
    print("\n  ⚠️  このCLIでは active化・READY化・draft_only解除を行いません")
    print("  ⚠️  現時点での結果は常に BLOCKED / NOT_READY です")


def print_summary(account_id: str) -> None:
    print(f"\n{'='*60}")
    print(f"  check_beauty_activation_readiness: {account_id}")
    print(f"{'='*60}")
    print(f"  PASS={PASS_COUNT}  WARN={WARN_COUNT}  NOT_READY={NOT_READY_COUNT}  BLOCKED={BLOCKED_COUNT}")
    print("  [RESULT] BLOCKED / NOT_READY — beauty_accountは現時点でactive化不可")
    print("  実際の活性化は: docs/beauty-account-activation-checklist.md を参照")


def main() -> None:
    parser = argparse.ArgumentParser(description="beauty_account活性化条件チェック")
    parser.add_argument("--account-id", default="beauty_account")
    parser.add_argument("--mock", action="store_true", help="モックモード")
    args = parser.parse_args()

    account_id = args.account_id

    print(f"\n=== check_beauty_activation_readiness ===")
    print(f"  account_id : {account_id}")
    print(f"  mock       : {args.mock}")
    print(f"\n  ⚠️  このCLIはactive化・READY化・実投稿を行いません")

    check_draft_only_status(account_id)
    check_thread_series_count(mock=args.mock)
    check_human_review_count(mock=args.mock)
    check_medical_risk()
    check_forbidden_keywords()
    check_allow_real_post()
    print_activation_checklist()
    print_summary(account_id)


if __name__ == "__main__":
    main()
