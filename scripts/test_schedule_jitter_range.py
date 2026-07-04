#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    texts = [(ROOT / f".github/workflows/{name}").read_text(encoding="utf-8") for name in ("autonomous-growth-loop-night-scout.yml", "autonomous-growth-loop-liver-manager.yml")]
    ok = all("random.randint(0, 1800)" in t and "time.sleep(delay)" in t and "[jitter] sleeping" in t for t in texts)
    print(f"  {'PASS' if ok else 'FAIL'} schedule jitter 0-1800 seconds")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
