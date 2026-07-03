#!/usr/bin/env python3
from generate_threads_ideas_from_references import build_thread_body
from public_post_quality import final_public_post_validator


def main() -> int:
    body = build_thread_body("night_scout", {"text": "参考テーマ"}, {}, 1)
    result = final_public_post_validator(body, "night_scout")
    ok = result["status"] == "PASS" and "今回の切り口" not in body
    print(f"  {'PASS' if ok else 'FAIL'} night_scout generation reader-facing")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
