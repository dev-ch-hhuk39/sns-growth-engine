#!/usr/bin/env python3
from source_url_utils import normalize_source_url


def main() -> int:
    checks = [
        normalize_source_url("https://youtube.com/channel/UCzFzty7aEd4tw3NqCW6pkLQ?si=x") == "https://youtube.com/channel/UCzFzty7aEd4tw3NqCW6pkLQ",
        normalize_source_url("https://www.tiktok.com/@user5597696107300?_r=1&_t=ZS") == "https://www.tiktok.com/@user5597696107300",
        normalize_source_url("https://www.tiktok.com/@uare.inc/?x=1") == "https://www.tiktok.com/@uare.inc",
    ]
    ok = all(checks)
    print(f"  {'PASS' if ok else 'FAIL'} source URL normalization removes query params")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
