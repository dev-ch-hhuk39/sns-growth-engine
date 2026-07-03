#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    source = (ROOT / "scripts/process_threads_queue.py").read_text(encoding="utf-8")
    ok = "extract_public_post_text" in source and "publisher.publish(\n        text," in source
    print(f"  {'PASS' if ok else 'FAIL'} publisher receives extracted public text")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
