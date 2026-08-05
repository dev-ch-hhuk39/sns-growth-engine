#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_scheduled_autopost_readonly_audit.py"
spec = importlib.util.spec_from_file_location("readonly_audit", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

assert len(module.ALL_SLOTS) == 10
assert len(module.TEXT_SLOTS) == 6
assert len(module.MEDIA_SLOTS) == 4
assert len(module.PROTECTED_QUEUE_IDS) == 4

noise = module.assess_text_quality(
    "夜職で店を選ぶとき『[音楽]エピグループが全部支援します』という話を確認してください。",
    "night_scout",
)
assert "transcript_noise_present" in noise["flags"]
assert "organization_or_brand_reference_present" in noise["flags"]
assert "quote_heavy_or_verbatim_risk" in noise["flags"]

clean = module.assess_text_quality(
    "僕が店選びで最初に確認してほしいのは、時給より控除とバックの計算方法。入店前に項目を分けて質問すると、実際の手取りを判断しやすくなる。",
    "night_scout",
)
assert "transcript_noise_present" not in clean["flags"]

source = SCRIPT.read_text(encoding="utf-8")
for forbidden in (
    "append_row(",
    "update_cell(",
    "batch_update(",
    "save_draft(",
    "process_threads_queue.py",
    "threads_publisher.py",
    "run_hybrid_ai_queue_gate.py",
    "client.log(",
    "update_queue_item(",
    "SheetsBudgetLedger",
):
    assert forbidden not in source, forbidden

print("PASS test_scheduled_autopost_readonly_audit.py")
