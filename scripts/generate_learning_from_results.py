"""
generate_learning_from_results.py - 結果から改善提案生成（Phase 5.4）

posted_results を分析し、改善提案を WAITING_REVIEW ステータスで
prompt_improvement_suggestions タブへ保存する。

禁止事項:
  - learning_rules.active=true の自動設定
  - prompt/code の自動書き換え
  - SNS投稿
  - 本番APIへの直接接続

使い方:
  python scripts/generate_learning_from_results.py --account-id night_scout --dry-run
  python scripts/generate_learning_from_results.py --account-id night_scout --use-sheets --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

from learning.post_result_analyzer import PostResultAnalyzer
from learning.improvement_suggester import ImprovementSuggester

try:
    from seeds import ACCOUNT_FORBIDDEN_KEYWORDS, ACCOUNT_FORBIDDEN_THEMES
except ImportError:
    ACCOUNT_FORBIDDEN_KEYWORDS: dict = {}
    ACCOUNT_FORBIDDEN_THEMES: dict = {}


# ------------------------------------------------------------------ #
# Sheets からデータ取得
# ------------------------------------------------------------------ #

def get_posted_results(account_id: str | None) -> list[dict]:
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
            except Exception:
                pass
        results = getattr(sheets, "_posted_results", [])
        if account_id:
            results = [r for r in results if r.get("account_id") == account_id]
        return results
    except (ValueError, Exception):
        from sheets_client import MockSheetsClient
        sheets = MockSheetsClient(dry_run=True)
        results = getattr(sheets, "_posted_results", [])
        if account_id:
            results = [r for r in results if r.get("account_id") == account_id]
        return results


# ------------------------------------------------------------------ #
# forbidden 矛盾チェック
# ------------------------------------------------------------------ #

def check_forbidden_conflict(suggestion: dict, account_id: str) -> tuple[bool, str]:
    analyzer = PostResultAnalyzer()
    keywords = ACCOUNT_FORBIDDEN_KEYWORDS.get(account_id, [])
    themes = ACCOUNT_FORBIDDEN_THEMES.get(account_id, [])
    text = str(suggestion.get("suggestion_text", suggestion.get("content", "")))
    return analyzer.detect_forbidden_conflict(text, keywords, themes)


# ------------------------------------------------------------------ #
# 改善提案の保存
# ------------------------------------------------------------------ #

def save_suggestions(suggestions: list[dict], dry_run: bool, use_sheets: bool) -> None:
    if not use_sheets or dry_run:
        print(f"  [dry-run] {len(suggestions)} 件の改善提案（保存スキップ）")
        for s in suggestions[:3]:
            print(f"    - [{s.get('status')}] {s.get('suggestion_type', '')} : {str(s.get('content', ''))[:60]}")
        return

    try:
        from config_loader import get_config
        from sheets_client import SheetsClient
        cfg = get_config()
        sheets = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=False)
        for s in suggestions:
            sheets.append_row("prompt_improvement_suggestions", list(s.values()))
        print(f"  [OK] {len(suggestions)} 件の改善提案を WAITING_REVIEW で保存")
    except Exception as e:
        print(f"  [WARN] Sheets書き込みエラー: {e}")


# ------------------------------------------------------------------ #
# メイン
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(description="結果から改善提案生成（Phase 5.4）")
    parser.add_argument("--account-id", required=True, help="対象アカウントID")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="dry-run（デフォルト: true）")
    parser.add_argument("--use-sheets", action="store_true",
                        help="Sheetsへの書き込みを有効化（--dry-runとの組み合わせで制御）")
    args = parser.parse_args()

    print("=" * 60)
    print("  generate_learning_from_results.py - 改善提案生成（Phase 5.4）")
    print("=" * 60)
    print(f"[INFO] account_id={args.account_id}")
    print(f"[INFO] dry-run={args.dry_run} use-sheets={args.use_sheets}")
    print("[INFO] learning_rules.active=true の自動設定はしません")
    print("[INFO] prompt/code の自動書き換えはしません")

    # posted_results 取得
    results = get_posted_results(args.account_id)
    print(f"\n[INFO] posted_results: {len(results)} 件取得")

    # 分析
    analyzer = PostResultAnalyzer()
    metrics = analyzer.analyze(results, account_id=args.account_id)

    print(f"[INFO] 投稿数: {metrics.get('posted_count', 0)}")
    eng_rate = metrics.get("metrics", {}).get("engagement_rate", 0)
    print(f"[INFO] エンゲージメント率: {eng_rate:.2%}")

    # 改善提案生成
    suggester = ImprovementSuggester()
    suggestions = suggester.suggest(metrics, source="post_result_analyzer")
    print(f"[INFO] 改善提案候補: {len(suggestions)} 件")

    # forbidden 矛盾チェック
    safe_suggestions = []
    rejected_suggestions = []
    for s in suggestions:
        conflict, detail = check_forbidden_conflict(s, args.account_id)
        if conflict:
            s["status"] = "WAITING_REVIEW"
            s["forbidden_conflict"] = detail
            s["warn_message"] = f"forbidden矛盾: {detail} → 要REJECT確認"
            rejected_suggestions.append(s)
            print(f"  [WARN] forbidden矛盾: {detail} → WAITING_REVIEW（REJECT推奨）")
        else:
            s["status"] = "WAITING_REVIEW"
            safe_suggestions.append(s)

    # 全提案は WAITING_REVIEW で保存（active=true にしない）
    all_suggestions = safe_suggestions + rejected_suggestions
    for s in all_suggestions:
        s["status"] = "WAITING_REVIEW"
        s["generated_at"] = datetime.now(timezone.utc).isoformat()
        s["source"] = "post_result_analyzer"
        # learning_rules.active は絶対に true にしない
        s["active"] = "false"

    if all_suggestions:
        print(f"\n[INFO] WAITING_REVIEW で出力: {len(all_suggestions)} 件")
        for s in all_suggestions[:5]:
            print(f"  [{s.get('status')}] {s.get('suggestion_type', s.get('insight_type', ''))}: "
                  f"{str(s.get('content', s.get('suggestion_text', '')))[:60]}")
    else:
        print("\n[INFO] 改善提案なし（投稿数不足または問題なし）")

    # 保存
    save_suggestions(all_suggestions, dry_run=args.dry_run, use_sheets=args.use_sheets)

    print("\n[完了]")
    print("[注意] 全提案は status=WAITING_REVIEW です。人間の確認・承認が必要です。")
    print("[注意] learning_rules.active=true は自動設定しません。")
    print("[次のステップ] scripts/review_improvement_suggestions.py で内容を確認してください")


if __name__ == "__main__":
    main()
