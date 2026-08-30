#!/usr/bin/env python3

from pathlib import Path

workflow = Path(
    ".github/workflows/direct-media-preparation.yml"
).read_text(
    encoding="utf-8"
)

wrapper = Path(
    "scripts/promote_autonomous_direct_media_ready.py"
).read_text(
    encoding="utf-8"
)

promoter = Path(
    "scripts/promote_hybrid_approved_media.py"
).read_text(
    encoding="utf-8"
)

beauty = Path(
    ".github/workflows/beauty-threads-production.yml"
).read_text(
    encoding="utf-8"
)

assert (
    "Promote strict autonomous Direct Media to READY"
    in workflow
)

assert (
    "promote_autonomous_direct_media_ready.py"
    in workflow
)

assert (
    "matrix.account_id == 'beauty_account'"
    not in workflow
)

assert (
    'approval_mode="media"'
    in wrapper
)

assert (
    "autonomous_low_risk=True"
    in wrapper
)

assert (
    "--confirm-autonomous-ready"
    in workflow
)

assert (
    "args.confirm_autonomous_ready"
    in wrapper
)

assert "account_allows_autonomous_ready" in wrapper

for token in (
    "rights_not_allowed",
    "permission_not_approved",
    "validator_not_pass",
    "internal_leak_not_pass",
    "account_fit_not_pass",
    "hybrid_ai_gate_",
):
    assert token in promoter, token

assert (
    'status="READY"'
    in promoter
)

assert (
    'auto_publish="true" if autonomous_low_risk else "false"'
    in promoter
)

assert "steps.scheduled_queue.outputs.approved == 'true'" in beauty
assert "steps.scheduled_queue.outputs.human_approved" not in beauty
assert "WAITING_REVIEW" in beauty

print(
    "[PASS] all active managed accounts can strictly auto-promote Direct Media"
)

print(
    "[PASS] autonomous READY requires hybrid + rights + permission + validator gates"
)

print(
    "[PASS] Beauty uses autonomous_strict_beauty without fake human approval"
)
