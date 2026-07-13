#!/usr/bin/env python3
"""Source role normalization must not broaden X/beauty or media rights."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text())["sources"]
    approved = [s for s in sources if s.get("source_role") == "approved_media"]
    x = [s for s in sources if s.get("source_platform") == "x"]
    beauty = [s for s in sources if "beauty_account" in (s.get("target_account_ids") or [])]
    reference_auto = [s for s in sources if s.get("reference_autopilot_enabled")]
    checks = [
        ("approved media has consistent gated policy", bool(approved) and all(s.get("rights_status") == "approved_creator_clip" and s.get("media_policy") == "approved_gated" and s.get("can_reuse_media") is True for s in approved)),
        ("reference autopilot remains bounded Threads only", all(s.get("source_platform") == "threads" and s.get("fetch_enabled") is True and not s.get("manual_only") for s in reference_auto)),
        ("x remains fetch disabled", all(not s.get("fetch_enabled") for s in x)),
        ("beauty remains non-active/non-fetch", all(not s.get("active") and not s.get("fetch_enabled") for s in beauty)),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
