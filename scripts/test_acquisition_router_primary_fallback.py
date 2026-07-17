#!/usr/bin/env python3
"""PRIMARY succeeds alone; FALLBACK is used only after a primary failure."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from acquisition.router import AdapterRouter, BackendRoute, BackendFailure


class Adapter:
    backend_version = "test"
    def __init__(self, name, fail=False): self.backend_name, self.fail, self.calls = name, fail, 0
    def acquire(self, source, *, limit):
        self.calls += 1
        if self.fail: raise BackendFailure("planned")
        return [self.backend_name]


primary, fallback = Adapter("primary", True), Adapter("fallback")
router = AdapterRouter({"primary": primary, "fallback": fallback}, {"cap": BackendRoute("cap", "primary", ("fallback",), cooldown_seconds=1)})
result = router.route("cap", {"source_id": "s"}, limit=1)
checks = {"fallback selected": result.backend_name == "fallback", "primary called once": primary.calls == 1,
          "fallback called once": fallback.calls == 1, "fallback flagged": result.fallback_used}
for name, ok in checks.items(): print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
