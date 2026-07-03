#!/usr/bin/env python3
from public_post_quality import final_public_post_validator


def main() -> int:
    text = "今回の切り口は「threads / night_work_scout」。投稿案を生成する。"
    result = final_public_post_validator(text, "night_scout")
    ok = result["status"] == "BLOCKED" and "internal_terms" in result["blocked_reasons"]
    print(f"  {'PASS' if ok else 'FAIL'} internal terms blocked")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
