#!/usr/bin/env python3
"""A READY media slot must not silently become text when media gates are off."""
from __future__ import annotations

import os
import sys
import types

from backfill_missed_content_slots import MEDIA_POST_ENV, recover_slot


direct = types.ModuleType("run_direct_reference_media_pipeline")
direct.dispatch_ready = lambda *_args, **_kwargs: {"status": "DRY_RUN", "selected_queue_id": "q_ready_direct"}
fallback = types.ModuleType("run_slot_text_fallback")
fallback.build_plan = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("text fallback must not run"))
fallback.execute = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("text fallback must not run"))
sys.modules["run_direct_reference_media_pipeline"] = direct
sys.modules["run_slot_text_fallback"] = fallback

previous = {name: os.environ.pop(name, None) for name in MEDIA_POST_ENV}
try:
    result = recover_slot(
        object(),
        "night_scout",
        {"slot_id": "ns_1800_direct_media", "expected_post_type": "direct_reference_media"},
        apply=True,
    )
finally:
    for name, value in previous.items():
        if value is not None:
            os.environ[name] = value

assert result["status"] == "BLOCKED_MEDIA_GATE", result
assert result["reason"] == "ready_media_exists_but_media_post_gates_are_disabled", result
print("PASS test_recovery_ready_media_never_bypasses_gates.py")
