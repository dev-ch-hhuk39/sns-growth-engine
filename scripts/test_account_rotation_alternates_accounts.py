#!/usr/bin/env python3
from public_post_quality import independent_account_order


def main() -> int:
    result = independent_account_order(["night_scout", "liver_manager"])
    ok = result["ordered_accounts"] == ["night_scout", "liver_manager"] and result["cross_account_rotation"] is False
    print(f"  {'PASS' if ok else 'FAIL'} preserves independent account order")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
