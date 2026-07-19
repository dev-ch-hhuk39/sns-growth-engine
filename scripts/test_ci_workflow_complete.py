#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
checks = [
    ("unit and integration runner", "run_repository_tests.py" in text),
    ("syntax check", "compileall" in text),
    ("secret full history", "fetch-depth: 0" in text and "gitleaks/gitleaks-action@e0c47f" in text),
    ("dependency audit", "pypa/gh-action-pip-audit@1220774" in text),
    ("license audit", "test_external_library_registry.py" in text and "test_library_capability_matrix_complete.py" in text),
    ("workflow security", "test_all_workflows_safety_flags.py" in text),
    ("fork PR receives no production secrets", "secrets." not in text and "pull_request_target" not in text),
    ("standard runner only", "runs-on: ubuntu-latest" in text and "self-hosted" not in text),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
