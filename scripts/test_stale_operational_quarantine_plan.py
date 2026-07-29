#!/usr/bin/env python3
from datetime import datetime, timezone
from quarantine_stale_operational_rows import build_plan
now=datetime(2026,7,29,12,0,tzinfo=timezone.utc)
plan=build_plan({"queue":[{"queue_id":"q1","status":"PROCESSING","updated_at":"2026-07-29T08:00:00+00:00"}],"content_slot_runs":[{"slot_run_id":"s1","status":"CLAIMED","lease_expires_at":"2026-07-29T09:00:00+00:00"}],"media_assets":[{"media_asset_id":"m1","status":"UPLOADING","updated_at":"2026-07-29T11:30:00+00:00"}]},older_than_minutes=120,now=now)
checks=[("stale queue isolated",any(o["entity_id"]=="q1" for o in plan["operations"])),("stale lease isolated",any(o["entity_id"]=="s1" for o in plan["operations"])),("recent asset retained",not any(o["entity_id"]=="m1" for o in plan["operations"]))]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
