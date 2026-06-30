#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("seed_reference_posts_from_sources", ROOT / "scripts/seed_reference_posts_from_sources.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    src = (ROOT / "scripts/seed_reference_posts_from_sources.py").read_text(encoding="utf-8")
    rows = mod.build_reference_posts(mod.load_sources(ROOT / "config/source_accounts/default_sources.json"), account_id="liver_manager", limit=5)
    checks = [
        ("liver_manager 5件生成", len(rows) == 5),
        ("requests等で外部fetchしない", "requests." not in src and "urlopen(" not in src),
        ("X platform除外", all(r["source_platform"] != "x" for r in rows)),
        ("downloadしない", "download" not in " ".join(str(r) for r in rows).lower()),
        ("auto_postなし", all(r["status"] == "WAITING_SCORE" for r in rows)),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
