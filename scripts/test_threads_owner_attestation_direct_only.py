#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import seed_owner_attested_media_permissions as seed

threads = seed.permission_row({"source_id": "t", "source_platform": "threads", "target_account_id": "night_scout"}, "now")
youtube = seed.permission_row({"source_id": "y", "source_platform": "youtube", "target_account_id": "night_scout"}, "now")
checks = {"threads is direct only": threads["usage_mode"] == "direct_media_reuse", "threads cannot cut": threads["allow_cut"] == "false",
          "video remains clip enabled": youtube["usage_mode"] == "direct_and_clip" and youtube["allow_cut"] == "true"}
for name, ok in checks.items(): print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
