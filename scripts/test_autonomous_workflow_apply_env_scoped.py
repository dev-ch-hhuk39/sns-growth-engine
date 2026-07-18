#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    text = (ROOT / ".github/workflows/autonomous-growth-loop.yml").read_text(encoding="utf-8")
    apply_idx = text.index("- name: Apply autonomous Threads loop")
    before_apply = text[:apply_idx]
    apply_step = text[apply_idx:]
    checks = [
        ("publish disabled globally", 'PUBLISH_ENABLED: "false"' in before_apply),
        ("threads post disabled globally", 'ALLOW_REAL_THREADS_POST: "false"' in before_apply),
        ("publish enabled only in apply step", 'PUBLISH_ENABLED: "true"' not in before_apply and 'PUBLISH_ENABLED: "true"' in apply_step),
        ("threads enabled only in apply step", 'ALLOW_REAL_THREADS_POST: "true"' not in before_apply and 'ALLOW_REAL_THREADS_POST: "true"' in apply_step),
        ("x disabled in apply", 'ALLOW_REAL_X_POST: "false"' in apply_step),
        ("media/transcription disabled in apply", all(flag in apply_step for flag in [
            'ALLOW_VIDEO_DOWNLOAD: "false"',
            'ALLOW_VIDEO_CUT: "false"',
            'ALLOW_CLOUDINARY_UPLOAD: "false"',
            'ALLOW_TRANSCRIPTION_API: "false"',
        ])),
        ("account threads secrets passed", all(name in text for name in [
            "THREADS_ACCESS_TOKEN_NIGHT_SCOUT",
            "THREADS_USER_ID_NIGHT_SCOUT",
            "THREADS_ACCESS_TOKEN_LIVER_MANAGER",
            "THREADS_USER_ID_LIVER_MANAGER",
        ])),
        ("manual apply requires explicit confirm", any(gate in apply_step for gate in [
            "if: github.event_name == 'schedule' || github.event.inputs.confirm_autonomous == 'true'",
            "if: (github.event_name == 'schedule' || github.event.inputs.confirm_autonomous == 'true')",
            "if: github.event.inputs.confirm_autonomous == 'true'",
        ])),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
