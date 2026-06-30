#!/usr/bin/env python3
"""Media pilot should only count low-risk attached/uploaded media candidates."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/plan_media_mix.py"


def _load():
    spec = importlib.util.spec_from_file_location("plan_media_mix_for_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    approved = {
        "queue_id": "q_media",
        "platform": "threads",
        "status": "WAITING_REVIEW",
        "media_asset_id": "asset_1",
        "media_status": "ATTACHED",
        "media_reuse_risk": "low",
        "rights_status": "allowed",
    }
    high_risk = {
        "queue_id": "q_high",
        "platform": "threads",
        "status": "WAITING_REVIEW",
        "media_asset_id": "asset_2",
        "media_status": "ATTACHED",
        "media_reuse_risk": "high",
        "rights_status": "allowed",
    }
    text_only = {
        "queue_id": "q_text",
        "platform": "threads",
        "status": "WAITING_REVIEW",
        "media_asset_id": "",
        "media_status": "",
        "media_reuse_risk": "low",
        "rights_status": "allowed",
    }
    plan = mod.build_media_mix_plan([approved, high_risk, text_only], "all")
    checks = [
        ("approved low-risk counts", mod.is_media_candidate(approved) is True),
        ("high-risk rejected", mod.is_media_candidate(high_risk) is False),
        ("text-only rejected", mod.is_media_candidate(text_only) is False),
        ("plan includes only approved media", plan.get("media_queue_ids") == ["q_media"]),
        ("third-party policy documented", "third_party_media_never_reused" in plan.get("media_policy", "")),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
