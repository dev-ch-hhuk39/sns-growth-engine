#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from run_media_growth_engine import build_media_growth_plan  # noqa: E402
from generation.media_platform_policy import REFERENCE_PLATFORMS, normalize_platform  # noqa: E402
from media.rights_policy import rights_allows_media_use  # noqa: E402


def platform_of(row: dict) -> str:
    return normalize_platform(
        row.get("source_platform") or row.get("platform") or row.get("source_platform_alias"),
        str(row.get("source_url") or row.get("canonical_url") or row.get("canonical_video_url") or ""),
    )


def rights_of(row: dict) -> str:
    return str(row.get("rights_status") or row.get("rights_policy") or "")


def main() -> int:
    plan = build_media_growth_plan("liver_manager")
    selected = list(plan.get("selected_sources") or [])
    bad = [
        row for row in selected
        if platform_of(row) not in REFERENCE_PLATFORMS
        or not rights_allows_media_use(rights_of(row))
    ]
    source_results = list(plan.get("source_results") or [])
    ok = (
        bool(selected)
        and not bad
        and plan.get("rights_check") == "PASS"
        and plan.get("permission_evidence") == "PASS"
        and all(row.get("rights_check") == "PASS" for row in source_results)
        and all(row.get("permission_evidence") == "PASS" for row in source_results)
    )
    if not ok:
        print("selected=", [(r.get("source_id"), platform_of(r), rights_of(r)) for r in selected])
    print(f"  {'PASS' if ok else 'FAIL'} media growth selects only approved physical-media sources")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
