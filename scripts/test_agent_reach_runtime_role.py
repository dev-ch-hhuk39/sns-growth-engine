#!/usr/bin/env python3
"""Agent Reach remains optional, honest about channels, and analysis-only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from reference.fetchers.agent_reach_fetcher import (  # noqa: E402
    AgentReachFetcher,
    _agent_reach_commands,
)

routing = json.loads((ROOT / "config/source_backend_routing.json").read_text(encoding="utf-8"))
source = (ROOT / "src/reference/fetchers/agent_reach_fetcher.py").read_text(encoding="utf-8")
checks = {
    "analysis-only backend role": routing["backend_roles"]["agent_reach"] == "ANALYSIS_ONLY",
    "home venv is optional": ".agent-reach-venv" in source,
    "official version subcommand": all(command[-1] == "version" for command in _agent_reach_commands()),
    "generic reference platforms declared": {"threads", "tiktok", "web"} <= set(AgentReachFetcher.supported_platforms),
    "X generic fetch stays blocked": "X network fetch is disabled" in source,
    "no browser or cookie path": "storage-state" not in source and "playwright" not in source.lower(),
    "no publisher access": "publish(" not in source,
}
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
