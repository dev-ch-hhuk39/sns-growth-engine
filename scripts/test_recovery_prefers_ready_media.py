#!/usr/bin/env python3
"""Recovery must dispatch durable media inventory before text fallback."""
from __future__ import annotations

import os
import sys
import types

from backfill_missed_content_slots import MEDIA_POST_ENV, recover_slot


class Client:
    pass


calls: list[bool] = []


def dispatch_ready(_client, account_id, slot_id, *, dry_run):
    assert account_id == "night_scout"
    assert slot_id == "ns_1800_direct_media"
    calls.append(dry_run)
    if dry_run:
        return {"status": "DRY_RUN", "selected_queue_id": "q_ready_direct"}
    return {"status": "POSTED", "selected_queue_id": "q_ready_direct", "post_result": {"post_url": "https://www.threads.com/t/proof"}}


fallback = types.ModuleType("run_slot_text_fallback")
fallback.build_plan = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("text fallback must not run"))
fallback.execute = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("text fallback must not run"))
direct = types.ModuleType("run_direct_reference_media_pipeline")
direct.dispatch_ready = dispatch_ready
sys.modules["run_slot_text_fallback"] = fallback
sys.modules["run_direct_reference_media_pipeline"] = direct

previous = {name: os.environ.get(name) for name in MEDIA_POST_ENV}
try:
    for name in MEDIA_POST_ENV:
        os.environ[name] = "true"
    result = recover_slot(
        Client(),
        "night_scout",
        {"slot_id": "ns_1800_direct_media", "expected_post_type": "direct_reference_media"},
        apply=True,
    )
finally:
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

assert result["status"] == "POSTED", result
assert result["path"] == "saved_direct_reference_media", result
assert calls == [True, False], calls
print("PASS test_recovery_prefers_ready_media.py")
