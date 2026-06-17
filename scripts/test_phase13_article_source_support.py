#!/usr/bin/env python3
"""Verify note/article production sources are configured safely."""
from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    with open(os.path.join(_ROOT, "config/source_accounts/production_sources.example.json"), encoding="utf-8") as f:
        sources = json.load(f)["sources"]
    notes = [s for s in sources if s.get("source_platform") == "note"]
    checks = [
        ("note sources 6", len(notes) == 6),
        ("manual_url collection", all(s.get("collection_method") == "manual_url" for s in notes)),
        ("no media", all(s.get("media_policy") == "do_not_download" for s in notes)),
        ("no body copy", all(s.get("copy_policy") == "do_not_copy_body" for s in notes)),
        ("article fields", all({"title", "summary", "key_points", "replay_tip"}.issubset(set(s.get("article_extraction_fields", []))) for s in notes)),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
