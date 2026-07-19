#!/usr/bin/env python3
"""Token refresh/status output must never contain any token fragment or API body."""
from __future__ import annotations

import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_threads_token.py"


def _load():
    spec = importlib.util.spec_from_file_location("refresh_threads_token", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = _load()
    secret = "THAA-production-token-fragment-ZDZD"
    module._get_current_token = lambda _account_id: secret
    module._load_token = lambda _account_id: None

    status_output = io.StringIO()
    with redirect_stdout(status_output):
        module.show_status("night_scout")

    refresh_output = io.StringIO()
    with redirect_stdout(refresh_output):
        module.refresh("night_scout", dry_run=True)

    source = SCRIPT.read_text(encoding="utf-8")
    combined = status_output.getvalue() + refresh_output.getvalue()
    checks = [
        ("full token is absent", secret not in combined),
        ("token prefix is absent", secret[:4] not in combined),
        ("token suffix is absent", secret[-4:] not in combined),
        ("status reports presence only", "SET（値は非表示）" in combined),
        ("mask helper removed", "def _mask(" not in source),
        ("HTTP response body is never printed", "resp.text" not in source),
        ("refresh JSON is never printed", "access_token がありません: {data}" not in source),
    ]

    failed = [label for label, ok in checks if not ok]
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {label}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
