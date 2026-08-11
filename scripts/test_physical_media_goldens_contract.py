#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "config/physical_media_goldens.json").read_text(encoding="utf-8"))
rows = [*manifest["x_exact_statuses"], *manifest["youtube_goldens"]]
checks = {
    "four exact X statuses": len(manifest["x_exact_statuses"]) == 4,
    "two YouTube account goldens": {row["account_id"] for row in manifest["youtube_goldens"]} == {"night_scout", "liver_manager"},
    "all source text grounded": all(str(row.get("source_text") or "").strip() for row in rows),
    "source geometry preserved": manifest["preserve_source"] is True,
    "verification never writes or publishes": all(marker in (ROOT / "scripts/verify_physical_media_goldens.py").read_text(encoding="utf-8") for marker in ('"production_writes": False', '"sns_publish": False', '"publisher_eligible"')),
}
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
