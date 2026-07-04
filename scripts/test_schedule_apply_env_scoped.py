#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    checks = []
    for name in ("autonomous-growth-loop-night-scout.yml", "autonomous-growth-loop-liver-manager.yml"):
        text = (ROOT / f".github/workflows/{name}").read_text(encoding="utf-8")
        checks.append((name, 'PUBLISH_ENABLED: "false"' in text and 'ALLOW_REAL_THREADS_POST: "false"' in text and 'PUBLISH_ENABLED: "true"' in text and 'ALLOW_REAL_THREADS_POST: "true"' in text and "Apply autonomous Threads loop" in text))
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n} apply env scoped")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
