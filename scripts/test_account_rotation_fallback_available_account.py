#!/usr/bin/env python3
from public_post_quality import account_rotation_order


def main() -> int:
    config = {"account_rotation_strategy": {"account_rotation_enabled": True, "rotation_accounts": ["night_scout", "liver_manager"], "fallback_to_available_account": True}}
    result = account_rotation_order(["night_scout", "liver_manager"], config, [])
    ok = result["fallback_to_available_account"] is True and result["selected_account"] in {"night_scout", "liver_manager"}
    print(f"  {'PASS' if ok else 'FAIL'} fallback enabled")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
