"""
manage_source_accounts.py - source account registry管理CLI（Phase 8）

source registryの一覧・絞り込み・検証を行う。
実API取得・scraping・外部download禁止。source priority自動変更禁止。

使い方:
  python scripts/manage_source_accounts.py --list --dry-run
  python scripts/manage_source_accounts.py --account-id night_scout --active-only --validate --dry-run
  python scripts/manage_source_accounts.py --platform x --active-only --dry-run
  python scripts/manage_source_accounts.py --validate --dry-run --output-json
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

from reference.source_registry import (
    load_registry,
    filter_sources,
    validate_registry,
    assess_source_rights,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="source account registry管理CLI")
    parser.add_argument("--list", action="store_true", help="source一覧を表示")
    parser.add_argument("--account-id", default="", help="target_account_idで絞り込み")
    parser.add_argument("--platform", default="", help="platformで絞り込み")
    parser.add_argument("--active-only", action="store_true", help="active=trueのみ表示")
    parser.add_argument("--validate", action="store_true", help="registry検証")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--output-json", action="store_true", help="JSON出力")
    parser.add_argument("--registry-path", default="", help="カスタムregistryパス")
    args = parser.parse_args()

    registry_path = args.registry_path or None
    sources = load_registry(registry_path)

    print(f"\n=== manage_source_accounts ===")
    print(f"  registry: {registry_path or 'default'}")
    print(f"  total sources: {len(sources)}")
    print(f"  dry_run: {args.dry_run}")

    if args.validate:
        print("\n[VALIDATE] source registry検証")
        issues = validate_registry(sources)
        if not issues:
            print("  [PASS] 検証OK — 全source正常")
        else:
            for issue in issues:
                print(f"  [WARN] {issue['source_id']}: {issue['errors']}")
        print(f"  issues: {len(issues)}")

    filtered = sources
    if args.account_id:
        filtered = filter_sources(filtered, target_account_id=args.account_id, active_only=False, exclude_blocked=False)
    if args.platform:
        filtered = filter_sources(filtered, platform=args.platform, active_only=False, exclude_blocked=False)
    if args.active_only:
        filtered = [s for s in filtered if s.get("active", False) and not s.get("blocked", False)]

    if args.list or args.account_id or args.platform:
        print(f"\n[LIST] sources ({len(filtered)} 件)")
        for s in filtered:
            assessment = assess_source_rights(s)
            status_icon = "[PASS]" if assessment["can_collect"] else "[WARN]"
            active_label = "active" if s.get("active") else "inactive"
            blocked_label = " [BLOCKED]" if s.get("blocked") else ""
            print(
                f"  {status_icon} {s.get('source_id')} | "
                f"{s.get('source_platform')} | "
                f"{s.get('source_handle')} | "
                f"{active_label}{blocked_label} | "
                f"rights={s.get('rights_policy')} | "
                f"targets={s.get('target_account_ids')}"
            )
            if assessment["issues"]:
                for issue in assessment["issues"]:
                    print(f"         → {issue}")

    if args.output_json:
        output = {
            "sources": filtered,
            "total": len(filtered),
            "dry_run": args.dry_run,
        }
        print("\n[JSON OUTPUT]")
        print(json.dumps(output, ensure_ascii=False, indent=2))

    print(f"\n=== 完了 (dry_run={args.dry_run}) ===")
    print("  source priority自動変更はしていません")
    print("  実API/scraping/downloadはしていません")


if __name__ == "__main__":
    main()
