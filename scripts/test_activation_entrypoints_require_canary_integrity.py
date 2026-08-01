#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parent

shared = (root / "activation_integrity.py").read_text(encoding="utf-8")

gate = (root / "scheduled_publish_activation_gate.py").read_text(encoding="utf-8")

validator = (root / "validate_production_activation.py").read_text(encoding="utf-8")

activator = (root / "activate_scheduled_publish.py").read_text(encoding="utf-8")

checks = {
    "shared evaluates inventory": ("build_inventory(" in shared),
    "shared evaluates integrity": ("canary_source_integrity_report(" in shared),
    "shared rejects missing slots": ("missing_canary_slots" in shared),
    "shared does not import gate": ("scheduled_publish_activation_gate" not in shared),
    "shared does not import validator": ("validate_production_activation" not in shared),
    "gate imports shared module": ("from activation_integrity import" in gate),
    "gate does not import validator": ("from validate_production_activation import" not in gate),
    "validator imports shared module": ("from activation_integrity import" in validator),
    "validator does not import gate": (
        "from scheduled_publish_activation_gate import" not in validator
    ),
    "gate passes integrity": ("canary_integrity=integrity" in gate),
    "validator passes integrity": ("canary_integrity=integrity" in validator),
    "activator reports combined failure": (
        "activation_evidence_or_" "canary_integrity_incomplete" in activator
    ),
}

for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} " f"{name}")

if not all(checks.values()):
    raise SystemExit(1)

print("PASS " "test_activation_entrypoints_" "require_canary_integrity.py")
