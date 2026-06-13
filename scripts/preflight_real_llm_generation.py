"""
preflight_real_llm_generation.py - 実LLM生成前preflightチェック（Phase 8.G）

MOCK_LLM=false の実LLM生成テストを実施する前に、安全条件を確認する。
実LLM生成はここでは行わない。Preflight確認のみ。

使い方:
  python scripts/preflight_real_llm_generation.py --account-id night_scout --platform x --mock
  python scripts/preflight_real_llm_generation.py --account-id beauty_account --platform threads --mock

禁止事項:
  - 実SNS投稿
  - APIキー・.env中身の表示
  - beauty_accountの実投稿
  - PUBLISH_ENABLED=trueでの実行
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


def _add(level: str, label: str, msg: str) -> None:
    global PASS_COUNT, FAIL_COUNT, WARN_COUNT, BLOCKED_COUNT
    RESULTS.append((level, label, msg))
    icons = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]", "BLOCKED": "[BLOCKED]", "INFO": "[INFO]"}
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


def check_account(account_id: str) -> str:
    print(f"\n[1] アカウント確認: {account_id}")
    try:
        from accounts.account_config import load_account_config
        cfg = load_account_config(account_id)
        if cfg.is_draft_only():
            _add("WARN", "account", f"{account_id} はdraft_only。生成結果はWAITING_REVIEW止まり。")
            return "DRAFT_ONLY"
        if not cfg.is_active():
            _add("BLOCKED", "account", f"{account_id} はinactive。LLM生成不可。")
            return "BLOCKED"
        _add("PASS", "account", f"{account_id} はactive")
        return "READY"
    except FileNotFoundError:
        _add("WARN", "account", f"{account_id} のaccount_configなし。継続可能。")
        return "READY"


def check_publish_flags() -> None:
    print("\n[2] 本番フラグ確認")
    publish = os.environ.get("PUBLISH_ENABLED", "false").lower()
    x_post = os.environ.get("ALLOW_REAL_X_POST", "false").lower()
    threads_post = os.environ.get("ALLOW_REAL_THREADS_POST", "false").lower()

    if publish == "true":
        _add("FAIL", "PUBLISH_ENABLED", "PUBLISH_ENABLED=true は危険。実投稿になる可能性あり。")
    else:
        _add("PASS", "PUBLISH_ENABLED", "false（安全）")

    if x_post == "true":
        _add("WARN", "ALLOW_REAL_X_POST", "ALLOW_REAL_X_POST=true — 実X投稿が有効化されています")
    else:
        _add("PASS", "ALLOW_REAL_X_POST", "false（安全）")

    if threads_post == "true":
        _add("WARN", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_THREADS_POST=true — 実Threads投稿が有効化されています")
    else:
        _add("PASS", "ALLOW_REAL_THREADS_POST", "false（安全）")


def check_api_key_presence(platform: str) -> None:
    print(f"\n[3] APIキー存在確認 (platform={platform}) ※値は表示しません")
    if platform == "x":
        keys = ["GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
    else:
        keys = ["GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]

    llm_keys_found = False
    for k in keys:
        val = os.environ.get(k, "")
        if val and len(val) > 4:
            _add("PASS", k, "設定あり (値は非表示)")
            llm_keys_found = True
        else:
            _add("WARN", k, "未設定またはダミー値")

    if not llm_keys_found:
        _add("WARN", "llm_api_key", "有効なLLM APIキーが見つかりません。MOCK_LLM=trueが必要です。")


def check_content_safety_config(account_id: str) -> None:
    print(f"\n[4] content safety設定確認: {account_id}")
    try:
        from text_policy import load_text_policy
        policy = load_text_policy()
        forbidden = policy.get("forbidden_keywords", [])
        _add("PASS", "text_policy", f"forbidden_keywords: {len(forbidden)}件")
    except Exception as e:
        _add("WARN", "text_policy", f"text_policyロード不可: {e}")

    is_beauty = account_id == "beauty_account"
    if is_beauty:
        _add("WARN", "beauty_medical_risk", "beauty_account: 医療広告/薬機法リスクチェックが必要。生成結果はWAITING_REVIEW必須。")
    else:
        _add("PASS", "beauty_medical_risk", "beauty_account以外 — 医療広告チェック不要")


def check_mock_llm_flag() -> None:
    print("\n[5] MOCK_LLM確認")
    mock_llm = os.environ.get("MOCK_LLM", "true").lower()
    if mock_llm == "false":
        _add("WARN", "MOCK_LLM", "MOCK_LLM=false — 実LLM APIが呼ばれます。APIコストに注意。")
    else:
        _add("PASS", "MOCK_LLM", "MOCK_LLM=true (または未設定) — mock動作")


def print_summary(account_id: str, platform: str) -> None:
    print(f"\n{'='*60}")
    print(f"  preflight_real_llm_generation: {account_id} / {platform}")
    print(f"{'='*60}")
    print(f"  PASS={PASS_COUNT}  WARN={WARN_COUNT}  FAIL={FAIL_COUNT}  BLOCKED={BLOCKED_COUNT}")
    if FAIL_COUNT > 0:
        print("  [RESULT] FAIL — 実LLM生成は行えません")
    elif BLOCKED_COUNT > 0:
        print("  [RESULT] BLOCKED — このアカウントでのLLM生成は禁止されています")
    elif WARN_COUNT > 0:
        print("  [RESULT] WARN — 生成は可能ですが要確認事項があります")
    else:
        print("  [RESULT] PASS — 実LLM生成の前提条件を満たしています（実行は別途）")
    print(f"\n  ⚠️  このスクリプトは実LLM生成を行いません")
    print("  実LLM生成時は MOCK_LLM=false を設定し、1件ずつ実行してください")
    print("  実投稿は絶対に行わないでください")


def main() -> None:
    parser = argparse.ArgumentParser(description="実LLM生成前preflightチェック")
    parser.add_argument("--account-id", default="night_scout")
    parser.add_argument("--platform", default="x", choices=["x", "threads"])
    parser.add_argument("--mock", action="store_true", help="モックモード")
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()

    account_id = args.account_id
    platform = args.platform

    print(f"\n=== preflight_real_llm_generation ===")
    print(f"  account_id : {account_id}")
    print(f"  platform   : {platform}")
    print(f"  mock       : {args.mock}")
    print(f"  dry_run    : {args.dry_run}")

    account_status = check_account(account_id)
    check_publish_flags()
    check_api_key_presence(platform)
    check_content_safety_config(account_id)
    check_mock_llm_flag()
    print_summary(account_id, platform)


if __name__ == "__main__":
    main()
