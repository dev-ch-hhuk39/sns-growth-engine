#!/usr/bin/env python3
from public_post_quality import generate_production_post
from run_system_owned_media_canaries import _alignment, _build_visual_plan, _post_design


def check(condition: bool, name: str) -> None:
    assert condition, name


# Regression: the prior Liver Manager continuity image was blocked because the
# validator compared each claim against the entire storyboard.  The visual plan
# now derives directly from the accepted post design and stores claim evidence.
generated = generate_production_post(
    "liver_manager",
    batch_id="media_plan_contract",
    content_type="direct_image",
    attempt=0,
)
text = generated["public_post_text"]
design = _post_design(text, generated)
plan = _build_visual_plan("direct_image", design)
alignment = _alignment("liver_manager", text, design, plan, [])

check(design["primary_topic"], "structured primary topic exists")
check(plan["primary_topic"] == design["primary_topic"], "visual plan inherits primary topic")
check(plan["cta_intent"] == design["cta_intent"], "visual plan inherits CTA intent")
check(alignment["alignment_status"] == "PASS", "direct image alignment passes")
check(alignment["main_claim_coverage"] == 1.0, "all caption claims covered")
check(alignment["unsupported_claim_count"] == 0, "no unsupported visual claim")
check(alignment["visual_topic_match"] is True, "visual topic matches")
check(alignment["visual_cta_match"] is True, "visual CTA matches")
check(all(item["verified"] for item in alignment["claim_support"]), "claim evidence is explicit")

# A visual plan that drifts to a different topic must fail closed.
drifted = dict(plan)
drifted["visual_text"] = (
    "初見が入ったら今の話題を伝え、答えやすい質問でコメントへ参加してもらう。"
)
drifted["visual_claims"] = [
    "初見が入ったら今の話題を伝え、答えやすい質問でコメントへ参加してもらう。"
]
blocked = _alignment("liver_manager", text, design, drifted, [])
check(blocked["alignment_status"] == "BLOCKED", "topic drift blocks")
check(
    "visual_claim_coverage_incomplete" in blocked["alignment_blocked_reasons"]
    or "visual_topic_mismatch" in blocked["alignment_blocked_reasons"],
    "topic drift has evidence",
)

# Every media type uses the same post design rather than selecting a new topic.
for kind in ("direct_image", "direct_carousel", "direct_video", "generated_clip"):
    candidate_plan = _build_visual_plan(kind, design)
    check(candidate_plan["primary_topic"] == design["primary_topic"], f"{kind} primary topic")
    check(candidate_plan["visual_plan_version"] == "visual_plan_v1", f"{kind} plan version")
    check(candidate_plan["feature_schema_version"] == "post_features_v1", f"{kind} feature schema")

print("PASS test_system_owned_media_plan_contract.py")
