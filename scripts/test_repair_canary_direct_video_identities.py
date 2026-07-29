#!/usr/bin/env python3
from repair_canary_direct_video_identities import TARGETS, build_plan
from source_identity_repair_executor import apply_plan_in_memory

datasets = {"source_posts": [], "source_post_media": []}
for source_post_id, expected in TARGETS.items():
    datasets["source_posts"].append({"source_post_id": source_post_id, "source_id": expected["source_id"], "external_post_id": expected["external_post_id"], "canonical_post_url": "https://invalid.example/profile"})
    datasets["source_post_media"].append({"source_post_media_id": f"m_{source_post_id}", "source_post_id": source_post_id, "canonical_post_url": "https://invalid.example/profile", "media_index": "0"})
plan = build_plan(datasets)
assert len(plan["parent_repairs"]) == 2
result = apply_plan_in_memory(plan, datasets)
assert result["status"] == "APPLIED"
for row in result["datasets"]["source_posts"]:
    assert row["canonical_post_url"] == TARGETS[row["source_post_id"]]["canonical_post_url"]
print("PASS test_repair_canary_direct_video_identities.py")
