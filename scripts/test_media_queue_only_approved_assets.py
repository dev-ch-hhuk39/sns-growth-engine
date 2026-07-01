#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("queue", ROOT / "scripts/generate_media_post_queue.py")
queue = importlib.util.module_from_spec(spec); spec.loader.exec_module(queue)
approved = queue.build_queue_row({"media_asset_id": "m1", "account_id": "night_scout", "status": "APPROVED", "rights_status": "approved_creator_clip"})
third = queue.build_queue_row({"media_asset_id": "m2", "account_id": "night_scout", "status": "APPROVED", "rights_status": "third_party_reference_only"})
checks = [("approved queued", approved and approved["status"] == "WAITING_REVIEW"), ("third blocked", third is None), ("not ready", approved and approved["auto_publish"] == "false")]
bad = [n for n, ok in checks if not ok]
for n, ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
