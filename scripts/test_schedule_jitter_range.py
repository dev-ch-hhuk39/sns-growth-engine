#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    texts = [(ROOT / f".github/workflows/{name}").read_text(encoding="utf-8") for name in ("autonomous-growth-loop-night-scout.yml", "autonomous-growth-loop-liver-manager.yml")]
    ok = all(
        "random.randint" not in text
        and "time.sleep" not in text
        and "Enforce scheduled posting window" in text
        for text in texts
    )
    print(f"  {'PASS' if ok else 'FAIL'} schedules use bounded windows without idle jitter")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
