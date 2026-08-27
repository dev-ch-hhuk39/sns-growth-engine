#!/usr/bin/env python3
from pathlib import Path

path = Path(".github/workflows/media-preparation-scheduler.yml")
text = path.read_text(encoding="utf-8")

assert 'cron: "15 3 * * *"' in text
assert 'cron: "15 5 * * *"' in text
assert "\n  push:\n" not in text
assert "github.event_name == 'push'" not in text
assert "TARGET_ACCOUNT: all" in text
assert "direct-media-preparation.yml/dispatches" in text
assert "approved-source-clip-preparation.yml/dispatches" in text

print("[PASS] final media scheduler is schedule-only")
print("[PASS] Direct preparation covers all production accounts")
print("[PASS] Beauty approved-source clip preparation remains scheduled")
