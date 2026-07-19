#!/usr/bin/env python3
"""Agent-Reach integration must use its real doctor/WebChannel contract."""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from src.reference.fetchers.agent_reach_fetcher import AgentReachFetcher


agent_reach = types.ModuleType("agent_reach")
channels = types.ModuleType("agent_reach.channels")
web = types.ModuleType("agent_reach.channels.web")


class WebChannel:
    def read(self, url: str) -> str:
        return f"# Safe research page\nContent from {url}"


web.WebChannel = WebChannel
old = {name: sys.modules.get(name) for name in ("agent_reach", "agent_reach.channels", "agent_reach.channels.web")}
try:
    sys.modules.update({"agent_reach": agent_reach, "agent_reach.channels": channels, "agent_reach.channels.web": web})
    rows = AgentReachFetcher()._run_agent_reach("https://example.com/page", "web", 5)
finally:
    for name, value in old.items():
        if value is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = value

source = (ROOT / "src/reference/fetchers/agent_reach_fetcher.py").read_text(encoding="utf-8")
checks = [
    ("real WebChannel API", "WebChannel().read(url)" in source),
    ("nonexistent fetch command absent", '"agent-reach",\n            "fetch"' not in source),
    ("bounded normalized record", len(rows) == 1 and rows[0]["post_url"] == "https://example.com/page"),
    ("snapshot is truncated defensively", len(rows[0]["text"]) <= 20000),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
