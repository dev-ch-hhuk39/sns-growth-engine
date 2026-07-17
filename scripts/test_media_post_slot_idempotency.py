#!/usr/bin/env python3
"""A posted scheduled media slot must never call a publisher again."""
import run_media_production_pipeline as production


original = production.existing_slot_status
try:
    production.existing_slot_status = lambda *_args, **_kwargs: "POSTED_FALLBACK"
    result = production.execute(
        {
            "status": "PLAN_ONLY",
            "account_id": "liver_manager",
            "slot_id": "lm_1800_clip_media",
            "post_saved_media": True,
            "would_post_video": True,
        },
        object(),
    )
finally:
    production.existing_slot_status = original

checks = [
    ("posted slot is skipped", result.get("status") == "SKIPPED"),
    ("reason is explicit", result.get("reason") == "slot_already_posted"),
    ("publisher intent is cleared", result.get("would_post_video") is False),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
