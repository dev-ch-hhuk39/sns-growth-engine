#!/usr/bin/env python3
"""Print acquisition capabilities and local tool readiness without side effects."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.capability_registry import CapabilityRegistry  # noqa: E402


def _tool_status(row: dict[str, Any]) -> tuple[str, str]:
    tool = str(row.get("tool", ""))
    distribution = str(row.get("python_distribution", ""))
    if tool:
        path = shutil.which(tool)
        if not path:
            return "NOT_INSTALLED", ""
        if distribution:
            try:
                return "INSTALLED", importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                pass
        return "INSTALLED", Path(path).name
    if distribution:
        try:
            return "INSTALLED", importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            return "NOT_INSTALLED", ""
    return "NOT_APPLICABLE", ""


def build_report(registry: CapabilityRegistry | None = None) -> dict[str, Any]:
    registry = registry or CapabilityRegistry.load()
    rows: list[dict[str, Any]] = []
    primary_missing: list[str] = []
    for item in registry.matrix():
        status, version = _tool_status(item)
        row = {
            "backend_id": item["backend_id"],
            "platforms": item.get("platforms", []),
            "role": item.get("role", "REJECT"),
            "production_selectable": registry.get(item["backend_id"]).production_selectable,
            "requires_auth": item.get("requires_auth", False),
            "requires_browser": item.get("requires_browser", False),
            "requires_external_service": item.get("requires_external_service", False),
            "health": item.get("health", "UNKNOWN"),
            "tool_status": status,
            "detected_version": version,
            "pin": item.get("pin", ""),
        }
        rows.append(row)
        if row["role"] == "PRIMARY" and status == "NOT_INSTALLED" and item.get("tool") not in {"python3"}:
            primary_missing.append(str(item["backend_id"]))
    return {
        "status": "PASS" if not primary_missing else "DEGRADED",
        "side_effects": False,
        "secret_values_read": False,
        "primary_missing": primary_missing,
        "backends": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"ACQUISITION_DOCTOR={report['status']}")
        for row in report["backends"]:
            print(
                "\t".join(
                    [
                        row["backend_id"],
                        row["role"],
                        ",".join(row["platforms"]),
                        row["tool_status"],
                        row["health"],
                    ]
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
