#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    text = (ROOT / "docs/video-reference-runbook.md").read_text(encoding="utf-8") + "\n" + (ROOT / "docs/growth-loop-runbook.md").read_text(encoding="utf-8")
    required = [
        "TikTok account URL",
        "reference analysis only",
        "third-party",
        "download",
        "cut",
        "upload",
        "text-only Threads",
    ]
    ok = all(term in text for term in required)
    print(f"  {'PASS' if ok else 'FAIL'} video text-only reference docs updated")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
