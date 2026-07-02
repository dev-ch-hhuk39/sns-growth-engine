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
        ("pilot source mentioned", "src_lm_yt_cand_001" in text),
        ("channel url mentioned", "channel URL" in text),
        ("unavailable mentioned", "UNAVAILABLE" in text),
        ("individual video needed", "individual YouTube video URL" in text or "個別動画URL" in text),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
