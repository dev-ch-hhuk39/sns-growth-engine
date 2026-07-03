#!/usr/bin/env python3
from public_post_quality import account_rotation_order


def main() -> int:
    config = {"account_rotation_strategy": {"account_rotation_enabled": True, "rotation_accounts": ["night_scout", "liver_manager"]}}
    posted = [{"account_id": "night_scout", "platform": "threads", "status": "POSTED", "posted_at": "2026-07-03T00:00:00+00:00"}]
    result = account_rotation_order(["night_scout", "liver_manager"], config, posted)
    ok = result["selected_account"] == "liver_manager"
    print(f"  {'PASS' if ok else 'FAIL'} alternates after last posted")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
