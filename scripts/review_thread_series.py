"""
review_thread_series.py - thread_series レビュー CLI（Phase 6.2）

生成済みスレッドシリーズの内容をレビュー表示する。
禁止キーワード・文字数・draft_only チェックを行う。

使い方:
  python scripts/review_thread_series.py --account-id beauty_account
  python scripts/review_thread_series.py --account-id night_scout --platform threads
  python scripts/review_thread_series.py --series-json path/to/series.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

from generation.thread_series_generator import ThreadSeriesGenerator
from seeds import ACCOUNT_FORBIDDEN_KEYWORDS, ACCOUNT_FORBIDDEN_THEMES


def check_forbidden(text: str, account_id: str) -> list[str]:
    """禁止キーワードが含まれていないか確認する。"""
    kw_list = ACCOUNT_FORBIDDEN_KEYWORDS.get(account_id, [])
    return [kw for kw in kw_list if kw in text]


def review_series(series_data: dict, account_id: str) -> dict:
    """シリーズのレビュー結果を返す。"""
    issues: list[str] = []
    warnings: list[str] = []

    # draft_only チェック
    try:
        from accounts.account_config import load_account_config
        cfg = load_account_config(account_id)
        if cfg.is_draft_only():
            warnings.append(f"draft_only アカウント: {account_id}。全投稿は WAITING_REVIEW のみ可。")
    except FileNotFoundError:
        pass

    posts = series_data.get("posts", [])
    platform = series_data.get("platform", "x")
    char_soft = 120 if platform == "x" else 500
    char_hard = 140 if platform == "x" else 800

    for i, p in enumerate(posts):
        text = p.get("text", "")
        role = p.get("post_role") or p.get("role", "?")
        char_count = len(text)

        # 文字数チェック
        if char_count > char_hard:
            issues.append(f"投稿[{i}]({role}): {char_count}文字 > hard上限{char_hard}文字")
        elif char_count > char_soft:
            warnings.append(f"投稿[{i}]({role}): {char_count}文字 > soft上限{char_soft}文字（要確認）")

        # 禁止キーワードチェック
        violations = check_forbidden(text, account_id)
        if violations:
            issues.append(f"投稿[{i}]({role}): 禁止キーワード検出: {violations}")

        # ステータスチェック
        status = p.get("status", "")
        if status not in ("", "WAITING_REVIEW", "APPROVED", "REJECTED"):
            issues.append(f"投稿[{i}]({role}): 不正ステータス: {status}")

    return {
        "series_id": series_data.get("series_id", ""),
        "account_id": account_id,
        "platform": platform,
        "post_count": len(posts),
        "issues": issues,
        "warnings": warnings,
        "review_result": "FAIL" if issues else ("WARN" if warnings else "PASS"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="thread_series レビュー CLI")
    parser.add_argument("--account-id", default="beauty_account", help="アカウントID")
    parser.add_argument("--platform", default="x", choices=["x", "threads"])
    parser.add_argument("--theme", default="", help="テーマ（サンプル生成用）")
    parser.add_argument("--post-count", type=int, default=4)
    parser.add_argument("--series-json", default="", help="レビュー対象JSONファイルパス")
    args = parser.parse_args()

    print(f"\n=== review_thread_series: {args.account_id} ===")

    # シリーズデータ取得（JSON指定またはサンプル生成）
    if args.series_json and os.path.isfile(args.series_json):
        with open(args.series_json, encoding="utf-8") as f:
            series_data = json.load(f)
        print(f"  JSON読み込み: {args.series_json}")
    else:
        print("  サンプル生成（mock LLM）")
        generator = ThreadSeriesGenerator()
        theme = args.theme or f"{args.account_id} サンプルテーマ"
        series = generator.generate(
            account_id=args.account_id,
            platform=args.platform,
            theme=theme,
            post_count=args.post_count,
            mock_llm=True,
        )
        series_data = series.to_dict()

    result = review_series(series_data, args.account_id)

    print(f"\n--- レビュー結果: {result['review_result']} ---")
    print(f"  series_id  : {result['series_id']}")
    print(f"  post_count : {result['post_count']}")

    if result["issues"]:
        print("\n  [FAIL] 問題あり:")
        for issue in result["issues"]:
            print(f"    - {issue}")

    if result["warnings"]:
        print("\n  [WARN] 要確認:")
        for w in result["warnings"]:
            print(f"    - {w}")

    if not result["issues"] and not result["warnings"]:
        print("  問題なし。投稿候補として合格です。")

    print()
    for i, p in enumerate(series_data.get("posts", [])):
        role = p.get("post_role") or p.get("role", "?")
        text = p.get("text", "")
        status = p.get("status", "WAITING_REVIEW")
        print(f"  [{i}] ({role}) [{status}] {len(text)}文字")
        preview = text.replace("\n", " / ")[:80]
        print(f"      {preview}{'...' if len(text) > 80 else ''}")

    sys.exit(1 if result["review_result"] == "FAIL" else 0)


if __name__ == "__main__":
    main()
