#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from generation.context_selector import select_generation_context

context = select_generation_context(
    account_id="night_scout",
    posted_results=[{"account_id": "night_scout", "theme": "shop_selection", "posted_text": "x"}],
    metric_rows=[{"account_id": "night_scout", "metrics_status": "MEASURED", "views": 100, "likes": 10, "comments": 2}],
    category_scores=[{"account_id": "night_scout", "category_name": "移籍", "total_score": "88"}],
    learning_rules=[{"account_id": "night_scout", "rule_id": "lr1", "status": "WAITING_REVIEW", "active": "false"}],
)
assert context["selected_theme"] != "shop_selection"
assert context["measured_post_count"] == 1
assert context["learning_rule_candidates"] == ["lr1"]
assert context["learning_rules_auto_applied"] is False
print("PASS test_generation_context_selector.py")
