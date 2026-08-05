#!/usr/bin/env python3
"""Manual media proofs remain plan-only; every real media post is Hybrid-gated."""
from pathlib import Path

from run_direct_reference_media_pipeline import build_plan

ROOT = Path(__file__).resolve().parents[1]
media_workflow = (ROOT / ".github/workflows/media-growth-post-liver-manager.yml").read_text(encoding="utf-8")
direct_workflow = (ROOT / ".github/workflows/direct-reference-media-liver-manager.yml").read_text(encoding="utf-8")
night_direct_workflow = (ROOT / ".github/workflows/direct-reference-media-night-scout.yml").read_text(encoding="utf-8")

manual_plan = build_plan("liver_manager", "", None, apply=False, manual_e2e_proof=True)
invalid_plan = build_plan("liver_manager", "lm_1600_direct_media", None, apply=False, manual_e2e_proof=True)
checks = [
    ("manual proof can plan without a slot", manual_plan.get("status") == "PLAN_ONLY" and manual_plan.get("slot_id") == ""),
    ("manual proof cannot claim a scheduled slot", invalid_plan.get("status") == "BLOCKED"),
    ("generated proof is workflow_dispatch-only", "github.event_name == 'workflow_dispatch'" in media_workflow and "manual_e2e_proof == 'true'" in media_workflow),
    ("direct manual dispatch requires confirmation", "workflow_dispatch:" in direct_workflow and "confirm_direct_media == 'true'" in direct_workflow),
    ("night direct manual dispatch requires confirmation", "workflow_dispatch:" in night_direct_workflow and "confirm_direct_media == 'true'" in night_direct_workflow),
    (
        "generated manual proof cannot bypass Hybrid AI",
        "[BLOCKED] manual_e2e_proof cannot bypass Hybrid AI" in media_workflow
        and "Post one manual E2E saved media proof" in media_workflow,
    ),
    (
        "scheduled generated media has no text fallback",
        "--prepare-saved-media-queue" in media_workflow
        and "run_hybrid_ready_pipeline.py" in media_workflow
        and "process_threads_queue.py" in media_workflow
        and '--queue-id "$qid"' in media_workflow
        and "--fallback-to-text" not in media_workflow,
    ),
    ("direct dispatcher uses READY inventory", "--post-ready" in direct_workflow and "ingest_direct_reference_media.py" not in direct_workflow),
    ("X stays blocked", 'ALLOW_REAL_X_POST: "false"' in media_workflow and 'ALLOW_REAL_X_POST: "false"' in direct_workflow),
    ("direct dispatcher does not prepare media", "--prepare-only" not in direct_workflow and 'ALLOW_CLOUDINARY_UPLOAD: "true"' not in direct_workflow),
    ("night dispatcher does not prepare media", "--prepare-only" not in night_direct_workflow and 'ALLOW_CLOUDINARY_UPLOAD: "true"' not in night_direct_workflow),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
