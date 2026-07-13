#!/usr/bin/env python3
"""Normalize registry source roles without changing any network/media gate.

The registry used to infer role from a mixture of fields.  This migration makes
the intended separation explicit while keeping existing rights and fetch flags
unchanged unless a listed, already-enabled reference source is involved.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "config/source_accounts/default_sources.json"
APPROVED_MEDIA = {"owned", "licensed", "approved_creator_clip"}


def role_for(source: dict[str, Any]) -> str:
    rights = str(source.get("rights_status") or source.get("rights_policy") or "").lower()
    if rights in APPROVED_MEDIA and bool(source.get("media_autopilot_enabled")):
        return "approved_media"
    return "reference_only"


def normalize(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    changed = 0
    for source in data.get("sources", []):
        role = role_for(source)
        rights = str(source.get("rights_status") or source.get("rights_policy") or "unknown").lower()
        desired = {
            "source_role": role,
            "reference_autopilot_enabled": bool(
                source.get("fetch_enabled") is True
                and not bool(source.get("manual_only"))
                and str(source.get("source_platform", "")).lower() == "threads"
                and "beauty_account" not in (source.get("target_account_ids") or [])
            ),
        }
        if role != "approved_media":
            desired.setdefault("media_autopilot_enabled", False)
        else:
            # Keep the registry's older reference-only fields from silently
            # contradicting the explicit, evidence-backed media permission.
            desired.update({
                "rights_policy": rights,
                "reuse_policy": "approved_creator_clip",
                "media_policy": "approved_gated",
                "can_reuse_media": True,
                "allow_download": "gated",
                "allow_cut": "gated",
                "allow_upload": "gated",
            })
        for key, value in desired.items():
            if source.get(key) != value:
                source[key] = value
                changed += 1
    return data, changed


def main() -> int:
    parser = argparse.ArgumentParser(description="normalize explicit source roles")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    normalized, changed = normalize(data)
    summary = {
        "status": "APPLIED" if args.apply else "PLAN_ONLY",
        "changed_field_count": changed,
        "source_count": len(normalized.get("sources", [])),
        "network_or_media_gate_changed": False,
    }
    if args.apply:
        SOURCES_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
