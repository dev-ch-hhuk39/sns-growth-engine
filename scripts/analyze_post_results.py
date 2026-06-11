"""
analyze_post_results.py - 投稿結果分析（Phase 5.4）

posted_results タブのデータを分析して成果を可視化する。
PV系 / CV系を分けて分析し、top/bottom投稿とgeneration_mode比較を出力する。

外部API呼び出しなし。SNS投稿なし。

使い方:
  python scripts/analyze_post_results.py --account-id night_scout --mock
  python scripts/analyze_post_results.py --account-id night_scout
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

from learning.post_result_analyzer import PostResultAnalyzer


# ------------------------------------------------------------------ #
# Sheets からデータ取得
# ------------------------------------------------------------------ #

def get_posted_results(account_id: str | None, use_mock: bool) -> list[dict]:
    if use_mock:
        from sheets_client import MockSheetsClient
        sheets = MockSheetsClient(dry_run=True)
        results = getattr(sheets, "_posted_results", [])
        if account_id:
            results = [r for r in results if r.get("account_id") == account_id]
        return results

    try:
        from config_loader import get_config
        from sheets_client import SheetsClient
        cfg = get_config()
        sheets = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=True)
        if hasattr(sheets, "_sh"):
            try:
                ws = sheets._sh.worksheet("posted_results")
                rows = ws.get_all_records()
                if account_id:
                    rows = [r for r in rows if r.get("account_id") == account_id]
                return rows
            except Exception as e:
                print(f"[WARN] Sheets読み取りエラー: {e} → Mockにフォールバック")
        results = getattr(sheets, "_posted_results", [])
        if account_id:
            results = [r for r in results if r.get("account_id") == account_id]
        return results
    except ValueError:
        print("[WARN] Sheets認証情報未設定 → MockSheetsClientを使用")
        from sheets_client import MockSheetsClient
        sheets = MockSheetsClient(dry_run=True)
        results = getattr(sheets, "_posted_results", [])
        if account_id:
            results = [r for r in results if r.get("account_id") == account_id]
        return results


# ------------------------------------------------------------------ #
# 表示
# ------------------------------------------------------------------ #

def print_analysis(analysis: dict) -> None:
    print(f"\n  アカウント: {analysis.get('account_id') or '全アカウント'}")
    print(f"  プラットフォーム: {analysis.get('platform') or '全プラットフォーム'}")
    print(f"  投稿数: {analysis.get('posted_count', 0)} 件")

    metrics = analysis.get("metrics", {})
    if not metrics:
        print("  [INFO] 分析対象データなし")
        return

    eng_rate = metrics.get("engagement_rate", 0)
    avg = metrics.get("average", {})
    total = metrics.get("total", {})

    print(f"\n  [全体指標]")
    print(f"    エンゲージメント率: {eng_rate:.2%}")
    print(f"    平均impression: {avg.get('impressions', 0):.1f}")
    print(f"    平均like: {avg.get('likes', 0):.1f}")
    print(f"    平均repost: {avg.get('reposts', 0):.1f}")
    print(f"    合計impression: {total.get('impressions', 0)}")
    print(f"    合計like: {total.get('likes', 0)}")

    # PV / CV
    pv = analysis.get("pv_metrics", {})
    cv = analysis.get("cv_metrics", {})
    print(f"\n  [PV系指標（リーチ）]")
    for k, v in pv.get("average", {}).items():
        print(f"    avg {k}: {v:.1f} (total: {pv.get('total', {}).get(k, 0)})")

    print(f"\n  [CV系指標（行動）]")
    for k, v in cv.get("average", {}).items():
        print(f"    avg {k}: {v:.1f} (total: {cv.get('total', {}).get(k, 0)})")

    # Top投稿
    top = analysis.get("top_posts", [])
    if top:
        print(f"\n  [Top投稿 (最大5件)]")
        for i, post in enumerate(top[:5], 1):
            imp = post.get("impressions", 0)
            likes = post.get("likes", 0)
            pid = post.get("result_id", post.get("queue_id", f"#row{i}"))
            text = str(post.get("text", post.get("body", "")))[:50]
            print(f"    {i}. [{pid}] imp={imp} likes={likes} | {text!r}")

    # Bottom投稿
    bottom = analysis.get("bottom_posts", [])
    if bottom:
        print(f"\n  [Bottom投稿 (最大5件)]")
        for i, post in enumerate(bottom[:5], 1):
            imp = post.get("impressions", 0)
            likes = post.get("likes", 0)
            pid = post.get("result_id", post.get("queue_id", f"#row{i}"))
            text = str(post.get("text", post.get("body", "")))[:50]
            print(f"    {i}. [{pid}] imp={imp} likes={likes} | {text!r}")

    # generation_mode別
    by_mode = analysis.get("by_generation_mode", {})
    if by_mode:
        print(f"\n  [generation_mode別]")
        for mode, mode_metrics in by_mode.items():
            count = mode_metrics.get("count", 0)
            mode_eng = mode_metrics.get("engagement_rate", 0)
            print(f"    {mode}: {count}件 | eng_rate={mode_eng:.2%}")


# ------------------------------------------------------------------ #
# メイン
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(description="投稿結果分析（Phase 5.4）")
    parser.add_argument("--account-id", help="対象アカウントID")
    parser.add_argument("--platform", help="プラットフォーム絞り込み（x / threads）")
    parser.add_argument("--mock", action="store_true", help="MockSheetsClientを使用")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    args = parser.parse_args()

    print("=" * 60)
    print("  analyze_post_results.py - 投稿結果分析（Phase 5.4）")
    print("=" * 60)
    print("[INFO] 外部API呼び出しなし。SNS投稿なし。")

    results = get_posted_results(args.account_id, use_mock=args.mock or True)
    print(f"\n[INFO] posted_results: {len(results)} 件取得")

    analyzer = PostResultAnalyzer()
    analysis = analyzer.analyze(
        results,
        account_id=args.account_id,
        platform=args.platform,
    )

    if args.json:
        print("\n--- JSON OUTPUT ---")
        print(json.dumps(analysis, ensure_ascii=False, indent=2, default=str))
    else:
        print_analysis(analysis)

    print("\n[完了]")
    print("[次のステップ] python scripts/generate_learning_from_results.py --account-id <id> --dry-run")


if __name__ == "__main__":
    main()
