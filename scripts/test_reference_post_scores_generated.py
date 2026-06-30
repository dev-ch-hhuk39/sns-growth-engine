#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    seed = _load("seed_reference_posts_from_sources", ROOT / "scripts/seed_reference_posts_from_sources.py")
    score = _load("score_reference_posts", ROOT / "scripts/score_reference_posts.py")
    posts = seed.build_reference_posts(seed.load_sources(ROOT / "config/source_accounts/default_sources.json"), account_id="night_scout", limit=5)
    rows = score.build_scores(posts, "night_scout", "20260630000000")
    checks = [
        ("score 5件生成", len(rows) == 5),
        ("reference_post_idあり", all(r.get("reference_post_id") for r in rows)),
        ("collected_post_id一致", rows[0]["reference_post_id"] == posts[0]["post_id"]),
        ("REFERENCE_ONLY推奨", all(r["recommended_use"] == "REFERENCE_ONLY" for r in rows)),
        ("statusを持たない", all("status" not in r for r in rows)),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
