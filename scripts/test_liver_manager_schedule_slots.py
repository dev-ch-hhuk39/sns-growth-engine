#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    text = (ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml").read_text(encoding="utf-8")
    expected = ['cron: "4 1 * * *"', 'cron: "4 4 * * *"', 'cron: "4 12 * * *"']
    direct = (ROOT / ".github/workflows/direct-reference-media-liver-manager.yml").read_text(encoding="utf-8")
    media = (ROOT / ".github/workflows/media-growth-post-liver-manager.yml").read_text(encoding="utf-8")
    ok = (
        all(x in text for x in expected)
        and 'schedule:' not in direct
        and 'schedule:' not in media
        and "Canary gate" in direct
        and "Canary gate" in media
        and "16:00 is direct-reference media" in text
        and "18:00 is generated clip media" in text
    )
    print(f"  {'PASS' if ok else 'FAIL'} liver_manager text schedule and manual media slots")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
