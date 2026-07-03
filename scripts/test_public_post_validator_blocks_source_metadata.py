#!/usr/bin/env python3
from public_post_quality import final_public_post_validator


def main() -> int:
    text = "参照元 source_url=https://example.com queue_id=q1 の内容です。"
    result = final_public_post_validator(text, "night_scout")
    ok = result["status"] == "BLOCKED" and "source_metadata_or_url" in result["blocked_reasons"]
    print(f"  {'PASS' if ok else 'FAIL'} source metadata blocked")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
