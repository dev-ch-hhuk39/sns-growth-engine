#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    text = (
        (ROOT / "docs/autonomous-mode-runbook.md").read_text(encoding="utf-8")
        + "\n"
        + (ROOT / "docs/video-reference-runbook.md").read_text(encoding="utf-8")
    )
    checks = [
        ("tiktok mentioned", "TikTok" in text),
        ("video url required", "/video/" in text),
        ("todo skipped", "TODO" in text and "skipped" in text),
        ("no profile expansion", "profile" in text and "not expanded" in text),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
