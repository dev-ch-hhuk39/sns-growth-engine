"""Focused contract for the shared reference-first route selector."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from generation.content_mix_planner import plan_operational_threads_routes
from generation.reference_first_router import choose_reference_first_route, load_operational_mix


def passed_understanding() -> dict:
    return {
        "status": "PASS", "transcript_status": "PASS",
        "standalone_segment_confirmed": True, "standalone_story_score": 91,
        "clip_worthy": True,
    }


def main() -> None:
    for account_id in ("night_scout", "liver_manager"):
        mix = load_operational_mix(account_id)
        assert mix == {
            "new_text_generation": 10,
            "reference_text_generation": 35,
            "pdca_text_generation": 20,
            "direct_reference_media": 30,
            "approved_source_clip": 5,
        }
        routes = plan_operational_threads_routes(account_id, 20)
        assert routes.count("approved_source_clip") == 1
        assert routes.count("reference_text_generation") == 7
        assert routes.count("direct_reference_media") == 6

    forced = choose_reference_first_route(
        desired_route="approved_source_clip", source_has_direct_media_permission=True,
        content_understanding={"status": "PASS", "transcript_status": "PASS"},
    )
    assert forced["route"] == "direct_reference_media"
    assert forced["clip_eligible"] is False

    clip = choose_reference_first_route(
        desired_route="approved_source_clip", source_has_direct_media_permission=True,
        content_understanding=passed_understanding(),
    )
    assert clip["route"] == "approved_source_clip" and clip["clip_eligible"] is True

    no_permission = choose_reference_first_route(
        desired_route="direct_reference_media", source_has_direct_media_permission=False,
    )
    assert no_permission["status"] == "BLOCKED"
    assert "direct_media_permission_missing" in no_permission["reasons"]
    print("PASS reference-first routing: reference/quote=65%, clip=5%, forced clips blocked")


if __name__ == "__main__":
    main()
