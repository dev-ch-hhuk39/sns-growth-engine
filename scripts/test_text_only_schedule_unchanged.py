#!/usr/bin/env python3
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

EXPECTED = {
    "autonomous-growth-loop-night-scout.yml": {
        "45 4 * * *",
        "45 6 * * *",
        "45 15 * * *",
    },
    "autonomous-growth-loop-liver-manager.yml": {
        "45 0 * * *",
        "45 3 * * *",
        "45 11 * * *",
    },
}


def scheduled_crons(text: str) -> set[str]:
    data = yaml.safe_load(text)
    trigger = data.get("on") or data.get(True) or {}
    return {str(row["cron"]) for row in trigger.get("schedule", [])}


def main() -> int:
    checks: list[tuple[str, bool]] = []
    for name, expected in EXPECTED.items():
        text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
        checks.extend(
            [
                (f"{name} text cron unchanged", scheduled_crons(text) == expected),
                (f"{name} remains text pipeline", "run_scheduled_text_slot_pipeline.py" in text),
                (f"{name} explicitly denies media", 'ALLOW_MEDIA_POSTS: "false"' in text),
                (f"{name} explicitly denies media download", 'ALLOW_VIDEO_DOWNLOAD: "false"' in text),
                (f"{name} explicitly denies media cut", 'ALLOW_VIDEO_CUT: "false"' in text),
                (f"{name} explicitly denies cloudinary upload", 'ALLOW_CLOUDINARY_UPLOAD: "false"' in text),
                (f"{name} keeps X off", 'ALLOW_REAL_X_POST: "false"' in text),
            ]
        )

    failed = [label for label, ok in checks if not ok]
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {label}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
