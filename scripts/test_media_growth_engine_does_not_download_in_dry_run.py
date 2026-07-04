#!/usr/bin/env python3
from run_media_growth_engine import build_media_growth_plan

def main() -> int:
    plan = build_media_growth_plan("liver_manager")
    ok = plan["would_download"] is False and plan["media_plan"]["download_enabled"] is False
    print(f"  {'PASS' if ok else 'FAIL'} media growth does not download in dry-run")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
