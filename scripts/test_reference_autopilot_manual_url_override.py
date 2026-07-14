#!/usr/bin/env python3
"""An explicitly approved bounded Threads source may retain manual_url provenance."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from collect_source_posts import select_sources


def main() -> int:
    base = {
        "source_platform": "threads",
        "target_account_ids": ["night_scout"],
        "fetch_enabled": True,
        "collection_method": "manual_url",
        "manual_only": False,
    }
    allowed = {**base, "source_id": "approved", "reference_autopilot_enabled": True}
    manual = {**base, "source_id": "manual", "reference_autopilot_enabled": False}
    selected, skipped = select_sources([allowed, manual], account_id="night_scout", platform="threads")
    checks = [
        ("explicit reference autopilot source is selected", [s["source_id"] for s in selected] == ["approved"]),
        ("historical manual source remains skipped", skipped == [{"source_id": "manual", "url": "", "reason": "manual_only"}]),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
