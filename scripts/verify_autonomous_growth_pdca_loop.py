#!/usr/bin/env python3
"""Run the focused completion contracts for the autonomous growth/PDCA loop."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "test_feature_attribution_cycle.py",
    "test_auto_ready_requires_generation_contract.py",
    "test_generated_queue_lifecycle_status.py",
    "test_generation_quality_gates.py",
    "test_system_owned_media_plan_contract.py",
    "test_first_wave_canary_contract.py",
    "test_remaining_eight_canary_contract.py",
    "test_remaining_eight_publish_scope.py",
    "test_bounded_media_canary_plan.py",
    "test_live_canary_inventory_contract.py",
    "test_final_production_contracts.py",
    "test_reconcile_canary_read_after_write.py",
    "test_scheduled_publish_activation_gate.py",
    "test_activate_scheduled_publish.py",
    "test_autonomous_workflow_schedule_safe.py",
    "test_autonomous_workflow_schedule_enabled.py",
    "test_production_autopilot_aftercare_workflow.py",
    "test_aftercare_metrics_failure_continues.py",
    "test_all_workflows_safety_flags.py",
)


def run(command: list[str]) -> tuple[bool, str]:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    output = (result.stdout + "\n" + result.stderr).strip()
    return result.returncode == 0, output


def main() -> int:
    ok, output = run([sys.executable, "-m", "compileall", "-q", "src", "scripts"])
    if not ok:
        print("FAIL compileall")
        print("\n".join(output.splitlines()[-40:]))
        return 1
    print("PASS compileall")

    failures: list[tuple[str, str]] = []
    for test in TESTS:
        ok, output = run([sys.executable, str(ROOT / "scripts" / test)])
        print(f"{'PASS' if ok else 'FAIL'} {test}")
        if not ok:
            failures.append((test, "\n".join(output.splitlines()[-40:])))

    if failures:
        print(f"FAILED {len(failures)}/{len(TESTS)} contracts")
        for test, tail in failures:
            print(f"\n--- {test} ---\n{tail}")
        return 1
    print(f"PASS autonomous growth PDCA contracts: {len(TESTS)}/{len(TESTS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
