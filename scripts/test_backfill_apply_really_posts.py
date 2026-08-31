#!/usr/bin/env python3
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "scripts/backfill_missed_content_slots.py").read_text()
assert "from run_slot_text_fallback import build_plan, execute" in text
assert 'else "BACKFILLED"' in text
assert 'else "OPERATIONAL_FAILURE"' in text
assert "_complete_post" in text
assert "--confirm-backfill" in text
print("PASS test_backfill_apply_really_posts.py")
