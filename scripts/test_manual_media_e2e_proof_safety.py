#!/usr/bin/env python3
"""Manual production proof is dispatch-only and never claims a timed slot."""
from pathlib import Path

from run_direct_reference_media_pipeline import build_plan

ROOT = Path(__file__).resolve().parents[1]
media_workflow = (ROOT / ".github/workflows/media-growth-post-liver-manager.yml").read_text(encoding="utf-8")
direct_workflow = (ROOT / ".github/workflows/direct-reference-media-liver-manager.yml").read_text(encoding="utf-8")

manual_plan = build_plan("liver_manager", "", None, apply=False, manual_e2e_proof=True)
invalid_plan = build_plan("liver_manager", "lm_1600_direct_media", None, apply=False, manual_e2e_proof=True)
checks = [
    ("manual proof can plan without a slot", manual_plan.get("status") == "PLAN_ONLY" and manual_plan.get("slot_id") == ""),
    ("manual proof cannot claim a scheduled slot", invalid_plan.get("status") == "BLOCKED"),
    ("generated proof is workflow_dispatch-only", "github.event_name == 'workflow_dispatch'" in media_workflow and "manual_e2e_proof == 'true'" in media_workflow),
    ("direct proof is workflow_dispatch-only", "github.event_name == 'workflow_dispatch'" in direct_workflow and "manual_e2e_proof == 'true'" in direct_workflow),
    ("generated proof has no text fallback", "--post-saved-media --apply --confirm-production-media --use-sheets" in media_workflow),
    ("direct proof has no text fallback", "--manual-e2e-proof --apply --confirm-direct-media --use-sheets" in direct_workflow),
    ("X stays blocked", 'ALLOW_REAL_X_POST: "false"' in media_workflow and 'ALLOW_REAL_X_POST: "false"' in direct_workflow),
    ("manual proof does not prepare media", "manual_e2e_proof != 'true'" in direct_workflow),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
