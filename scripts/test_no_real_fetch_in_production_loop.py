#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    seed_src = (ROOT / "scripts/seed_reference_posts_from_sources.py").read_text(encoding="utf-8")
    gen_src = (ROOT / "scripts/generate_threads_ideas_from_references.py").read_text(encoding="utf-8")
    checks = [
        ("seedでnetwork fetchなし", "requests." not in seed_src and "urlopen(" not in seed_src),
        ("seedでyt_dlpなし", "yt_dlp" not in seed_src),
        ("seedでtranscriptionなし", "transcrib" not in seed_src.lower()),
        ("generateでpublisher呼び出しなし", "ThreadsPublisher" not in gen_src),
        ("generateでCloudinaryなし", "cloudinary" not in gen_src.lower()),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
