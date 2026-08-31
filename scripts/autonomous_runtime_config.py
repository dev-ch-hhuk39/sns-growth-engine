#!/usr/bin/env python3
"""Load autonomous publication policy from one authoritative config."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUTONOMOUS_CONFIG = ROOT / "config" / "autonomous_mode.json"
APPROVAL_RULES = ROOT / "config" / "auto_approval_rules.json"
AUTHORITY_PATH = "config/autonomous_mode.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_runtime_configuration(
    autonomous: dict[str, Any],
    approval_rules: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    control = approval_rules.get("publication_control", {})
    if control.get("authority") != AUTHORITY_PATH:
        reasons.append("publication_authority_not_autonomous_mode")
    if "auto_post_enabled" in approval_rules.get("defaults", {}):
        reasons.append("duplicate_auto_post_authority")
    for required in (
        "autonomous_mode_enabled",
        "auto_ready_enabled",
        "auto_post_enabled",
        "scheduled_prepare_enabled",
        "scheduled_publish_enabled",
        "kill_switch",
    ):
        if required not in autonomous:
            reasons.append(f"autonomous_key_missing:{required}")
    if autonomous.get("auto_post_enabled") and not autonomous.get("autonomous_mode_enabled"):
        reasons.append("auto_post_requires_autonomous_mode")
    if autonomous.get("scheduled_publish_enabled") and not autonomous.get("auto_post_enabled"):
        reasons.append("scheduled_publish_requires_auto_post")
    if autonomous.get("scheduled_publish_enabled") and not autonomous.get("production_publish_activation_approved"):
        reasons.append("scheduled_publish_requires_activation_approval")
    return reasons


def load_runtime_policy(
    autonomous_path: Path = AUTONOMOUS_CONFIG,
    approval_path: Path = APPROVAL_RULES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    autonomous = _load(autonomous_path)
    approval_rules = _load(approval_path)
    reasons = validate_runtime_configuration(autonomous, approval_rules)
    if reasons:
        raise RuntimeError("invalid autonomous runtime configuration: " + ",".join(reasons))
    return autonomous, approval_rules
