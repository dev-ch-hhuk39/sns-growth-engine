#!/usr/bin/env python3
"""Only the publisher may apply the format-specific Threads media gate."""
from pathlib import Path


def main() -> int:
    source = (Path(__file__).resolve().parents[1] / "scripts" / "run_direct_reference_media_pipeline.py").read_text(encoding="utf-8")
    required = 'not _true(os.environ.get("ALLOW_MEDIA_POSTS"))'
    old_global_video_gate = 'or not _true(os.environ.get("ALLOW_REAL_THREADS_VIDEO_POST"))):\n        print(json.dumps({"status": "BLOCKED"'
    checks = [
        ("base media gate remains", required in source),
        ("dispatcher does not require video gate for every format", old_global_video_gate not in source),
        ("format-specific gate is not claimed by dispatcher", "all Threads media gates" not in source),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
