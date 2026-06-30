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
    gen = _load("generate_threads_ideas_from_references", ROOT / "scripts/generate_threads_ideas_from_references.py")
    posts = seed.build_reference_posts(seed.load_sources(ROOT / "config/source_accounts/default_sources.json"), account_id="night_scout", limit=3)
    scores = score.build_scores(posts, "night_scout", "20260630000000")
    rows = gen.build_generation_rows(account_id="night_scout", posts=posts, scores=scores, top_n=3)
    all_rows = rows["drafts"] + rows["social_derivatives"] + rows["queue"]
    checks = [
        ("queue 3件", len(rows["queue"]) == 3),
        ("全てWAITING_REVIEW", all(r["status"] == "WAITING_REVIEW" for r in all_rows)),
        ("READYなし", all(r["status"] != "READY" for r in all_rows)),
        ("auto_publish false", all(r["auto_publish"] == "false" for r in rows["queue"])),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
