#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    text = (ROOT / "scripts/run_autonomous_loop.py").read_text(encoding="utf-8")
    checks = [
        ("verify env created", "verify_env = dict(os.environ)" in text),
        ("verify publish false", 'verify_env["PUBLISH_ENABLED"] = "false"' in text),
        ("verify threads false", 'verify_env["ALLOW_REAL_THREADS_POST"] = "false"' in text),
        ("verify media false", 'verify_env["ALLOW_VIDEO_DOWNLOAD"] = "false"' in text and 'verify_env["ALLOW_CLOUDINARY_UPLOAD"] = "false"' in text),
        ("verify env passed", "env=verify_env" in text),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
