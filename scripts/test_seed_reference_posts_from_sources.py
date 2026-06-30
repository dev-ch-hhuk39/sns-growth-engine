#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/seed_reference_posts_from_sources.py"


def _load():
    spec = importlib.util.spec_from_file_location("seed_reference_posts_from_sources", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    sources = mod.load_sources(ROOT / "config/source_accounts/default_sources.json")
    rows = mod.build_reference_posts(sources, account_id="night_scout", limit=5)
    checks = [
        ("night_scout 5件生成", len(rows) == 5),
        ("source_account_posts schema keyあり", all("post_id" in r and "post_text" in r for r in rows)),
        ("REFERENCE_ONLY固定", all(r["use_status"] == "REFERENCE_ONLY" for r in rows)),
        ("media reuse不可", all(str(r["can_reuse_media"]).lower() == "false" for r in rows)),
        ("Xをseedしない", all(r["source_platform"] != "x" for r in rows)),
        ("実fetch情報なし", all(r["likes"] == "0" and r["views"] == "0" for r in rows)),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
