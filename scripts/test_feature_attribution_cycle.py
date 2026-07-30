#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from learning.feature_attribution import build_growth_cycle, preferred_primary_topics
from public_post_quality import generate_production_post


def check(condition: bool, name: str) -> None:
    assert condition, name


posted = []
snapshots = []
for index in range(10):
    strong = index < 5
    result_id = f"r{index}"
    topic = "work_conditions" if strong else "schedule_balance"
    posted.append({
        "result_id": result_id,
        "queue_id": f"q{index}",
        "account_id": "night_scout",
        "platform": "threads",
        "status": "POSTED",
        "content_type": "original_text",
        "generation_mode": "original_text",
        "feature_schema_version": "post_features_v1",
        "primary_topic": topic,
        "structure_variant": "1" if strong else "4",
        "cta_intent": "decision_support",
        "media_used": "false",
    })
    snapshots.append({
        "snapshot_id": f"s{index}",
        "result_id": result_id,
        "account_id": "night_scout",
        "collection_window_hours": "168",
        "metrics_status": "MEASURED",
        "views": 1000 + index * 10 if strong else 100 + index,
        "likes": 120 if strong else 2,
        "comments": 20 if strong else 0,
        "reposts": 10 if strong else 0,
        "follows": 15 if strong else 0,
        "collected_at": "2026-07-30T00:00:00Z",
    })

cycle = build_growth_cycle(posted, snapshots, account_id="night_scout")
check(cycle["observation_count"] == 10, "ten measured observations")
check(cycle["attribution_count"] == 10, "one attribution per result")
check(cycle["active_strategy_count"] > 0, "strategy activates only after sample threshold")
check(cycle["safety"]["causal_claims"] is False, "no causal overclaim")
check(cycle["safety"]["prompt_or_code_rewrite"] is False, "no prompt rewrite")
preferred = preferred_primary_topics(cycle["strategy_state"], "night_scout")
check(preferred and preferred[0] == "work_conditions", "strong topic preferred")
check(any("関連評価" in row["explanation"] for row in cycle["attributions"]), "explanation is evidence-qualified")


legacy = [{**posted[0], "result_id": "legacy", "feature_schema_version": ""}]
legacy_snapshots = [{**snapshots[0], "result_id": "legacy", "snapshot_id": "legacy_snapshot"}]
check(build_growth_cycle(legacy, legacy_snapshots, account_id="night_scout")["observation_count"] == 0, "legacy rows without feature provenance are ignored")

small = build_growth_cycle(posted[:2], snapshots[:2], account_id="night_scout")
check(all(row["outcome_label"] == "INSUFFICIENT_COMPARISON_DATA" for row in small["attributions"]), "small sample does not overlearn")
check(small["active_strategy_count"] == 0, "small sample keeps strategy observe-only")

selected = None
for index in range(30):
    candidate = generate_production_post(
        "night_scout",
        batch_id=f"policy_test_{index}",
        content_type="original_text",
        preferred_topics=["work_conditions"],
    )
    if candidate.get("generation_policy", {}).get("mode") == "bounded_exploit":
        selected = candidate
        break
check(selected is not None, "bounded exploit path reachable")
check(selected["generation_policy"]["exploration_rate"] == 0.20, "exploration retained")
check(selected["grounding_summary"]["quality_topic"] == "work_conditions", "active topic guides generation")

schema_source = (ROOT / "src" / "sheets_client.py").read_text(encoding="utf-8")
for field in (
    "feature_schema_version", "primary_topic", "structure_variant", "cta_intent",
    "post_design_json", "generation_policy_json",
):
    check(f'"{field}"' in schema_source, f"posted result stores {field}")
check('"post_attributions"' in schema_source, "attribution tab exists")
check('"strategy_state"' in schema_source, "strategy tab exists")

print("PASS test_feature_attribution_cycle.py")
