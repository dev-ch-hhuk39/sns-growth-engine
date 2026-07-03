#!/usr/bin/env python3
from public_post_quality import extract_public_post_text


def main() -> int:
    value = {"internal_analysis": "今回の切り口", "public_post_text": "夜職で店を選ぶ時、時給だけで決める子は危ない。自分が続けられる条件を整理することが大事。"}
    text = extract_public_post_text(value)
    ok = "今回の切り口" not in text and text.startswith("夜職")
    print(f"  {'PASS' if ok else 'FAIL'} public_post_text extracted")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
