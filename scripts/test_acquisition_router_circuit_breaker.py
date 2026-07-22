#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from acquisition.router import AdapterRouter, BackendRoute, BackendFailure

class Bad:
    backend_name = "bad"; backend_version = "test"
    def __init__(self): self.calls = 0
    def acquire(self, source, *, limit): self.calls += 1; raise BackendFailure("expected")

bad = Bad(); router = AdapterRouter({"bad": bad}, {"cap": BackendRoute("cap", "bad", cooldown_seconds=60)})
for _ in range(3):
    try: router.route("cap", {}, limit=1)
    except BackendFailure: pass
try: router.route("cap", {}, limit=1)
except BackendFailure: pass
checks = {
    "three failures are attempted before circuit": bad.calls == 3,
    "fourth attempt sees circuit open": "circuit_open" in router.states["bad"].last_failure_reason or router.health_rows()[0]["status"] == "COOLDOWN",
    "health is cooldown after threshold": router.health_rows()[0]["status"] == "COOLDOWN",
}
for name, ok in checks.items(): print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
