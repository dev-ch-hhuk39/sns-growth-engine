#!/usr/bin/env python3
from public_post_quality import final_public_post_validator


def main() -> int:
    result = final_public_post_validator("今回の切り口は source_id を参考にした投稿案です。", "night_scout")
    ok = result["status"] == "BLOCKED"
    print(f"  {'PASS' if ok else 'FAIL'} bad READY text blocked before publisher")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
