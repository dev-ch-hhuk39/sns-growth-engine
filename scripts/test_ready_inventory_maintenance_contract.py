#!/usr/bin/env python3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from maintain_text_ready_inventory import (
    _generation_commands,
    _ready_exists,
    _publishable_ready_rows,
    _reserve_status,
    _coverage_result,
    _required_text_slots,
    evergreen_theme_variants,
    future_text_slots,
    next_text_slot,
)

jst = timezone(timedelta(hours=9))
night = next_text_slot("night_scout", now=datetime(2026, 8, 31, 13, 0, tzinfo=jst))
assert night["slot_id"] == "ns_1400_reference", night
liver = next_text_slot("liver_manager", now=datetime(2026, 8, 31, 20, 0, tzinfo=jst))
assert liver["slot_id"] == "lm_2100_pdca", liver
night_24h = future_text_slots("night_scout", now=datetime(2026, 8, 31, 13, 0, tzinfo=jst))
assert [row["slot_id"] for row in night_24h] == [
    "ns_1400_reference", "ns_1600_original", "ns_2500_pdca"
]
resolved_mixed_routes = [
    {"slot_id": "text", "post_type": "reference_text"},
    {"slot_id": "media", "post_type": "direct_reference_media"},
]
with patch("maintain_text_ready_inventory.scheduled_slots", return_value=resolved_mixed_routes):
    assert _required_text_slots("night_scout", datetime.now(jst), datetime.now(jst) + timedelta(hours=1)) == [resolved_mixed_routes[0]]
pdca_routes = _generation_commands("liver_manager", liver)
assert [route for route, _command in pdca_routes] == ["measured_pdca", "safe_original_fallback", "offline_original_bank"]
assert "--offline-original" in pdca_routes[-1][1]
assert "--require-measured-pdca" in pdca_routes[0][1]
fallback_command = pdca_routes[1][1]
assert fallback_command[fallback_command.index("--post-type") + 1] == "original_text"
reference_routes = _generation_commands("night_scout", night)
assert [route for route, _command in reference_routes] == ["primary", "safe_original_fallback", "offline_original_bank"]
reference_fallback = reference_routes[1][1]
assert reference_fallback[reference_fallback.index("--post-type") + 1] == "original_text"
ready_contract = {
    "account_id": "night_scout",
    "slot_id": night["slot_id"],
    "status": "READY",
    "validator_status": "PASS",
    "internal_leak_status": "PASS",
    "account_fit_status": "PASS",
}
assert _ready_exists(
    [{**ready_contract, "schedule_date_jst": night["business_date_jst"]}],
    "night_scout",
    night,
)
assert _ready_exists(
    [{**ready_contract, "business_date_jst": night["business_date_jst"]}],
    "night_scout",
    night,
)
assert not _ready_exists(
    [{**ready_contract, "schedule_date_jst": "2026-09-01"}],
    "night_scout",
    night,
)
assert _reserve_status(0, 3) == "DELIVERY_SLO_FAILED"
assert _reserve_status(1, 3) == "RESERVE_DEGRADED"
assert _reserve_status(3, 3) == "DELIVERY_READY"
assert _coverage_result(10, 10) == ("PASS", 100.0, "")
assert _coverage_result(10, 9) == ("FAILED", 90.0, "")
assert _coverage_result(0, 0) == ("FAILED", 0.0, "NO_REQUIRED_TEXT_SLOTS")
variants = evergreen_theme_variants("liver_manager")
assert len(variants) >= 20 and len(variants) == len(set(variants))
assert all(any(category in variant for category in ("ライバーあるある", "配信で稼ぐリアル", "マネージャーの視点",
                                                      "TikTokライブ攻略", "ライバーメンタル", "ライバー成長記録",
                                                      "配信環境・機材", "ライバー収入の話")) for variant in variants)
publishable = {**ready_contract, "public_post_text": "配信の始め方を一つずつ整える。", "platform": "threads",
               "post_type": "reference_text", "queue_id": "q_publishable",
               "schedule_date_jst": night["business_date_jst"]}
with patch("maintain_text_ready_inventory.final_public_post_validator", return_value={"status": "PASS"}), \
     patch("maintain_text_ready_inventory.hybrid_ai_gate_passed", return_value=(True, {})):
    assert _publishable_ready_rows(None, [publishable], "night_scout", night) == [publishable]
    assert _publishable_ready_rows(None, [{**publishable, "media_asset_id": "media"}], "night_scout", night) == []
    assert _publishable_ready_rows(None, [{**publishable, "post_type": "direct_reference_media"}], "night_scout", night) == []
source = Path(__file__).with_name("maintain_text_ready_inventory.py").read_text(encoding="utf-8")
assert "process_threads_queue.py" not in source
assert "--autonomous-low-risk" in source
assert "QUALITY_EXHAUSTED" in source
workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/autopilot-auto-ready.yml").read_text(encoding="utf-8")
assert "maintain_text_ready_inventory.py" in workflow
assert "--text-inventory-scope" in workflow
assert "GEMINI_API_KEY" in workflow
print("PASS test_ready_inventory_maintenance_contract.py")
