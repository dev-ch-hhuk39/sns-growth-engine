#!/usr/bin/env python3
"""import_reference_urls.build_plan の安全ゲートを検証する（委譲先は実行しない）。"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/import_reference_urls.py"


def _load():
    spec = importlib.util.spec_from_file_location("import_reference_urls", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _args(**kw):
    base = dict(source_file="config/source_accounts/default_sources.json", source_id="s1",
                platform="youtube", url="https://example.com/v", handle=None,
                target_account="liver_manager", collection_method="manual_url",
                name=None, category=None, apply=False, confirm_import=False)
    base.update(kw)
    return SimpleNamespace(**base)


def main() -> int:
    mod = _load()
    checks: list[tuple[str, bool]] = []

    p = mod.build_plan(_args())
    checks.append(("既定は PLAN_ONLY", p["status"] == "PLAN_ONLY"))
    checks.append(("既定で --no-dry-run なし", "--no-dry-run" not in p["delegate_argv"]))
    checks.append(("rights_status 既定 unknown", p["safety"]["rights_status_default"] == "unknown"))
    checks.append(("人手レビュー必須", p["safety"]["requires_human_review"] is True))
    checks.append(("download しない", p["safety"]["media_download"] is False))

    p2 = mod.build_plan(_args(apply=True))
    checks.append(("apply のみは PLAN_ONLY", p2["status"] == "PLAN_ONLY"))

    p3 = mod.build_plan(_args(apply=True, confirm_import=True))
    checks.append(("apply+confirm は WILL_WRITE", p3["status"] == "WILL_WRITE"))
    checks.append(("WILL_WRITE で --no-dry-run 付与", "--no-dry-run" in p3["delegate_argv"]))

    checks.append(("beauty 向けは BLOCKED",
                   mod.build_plan(_args(target_account="beauty_account"))["status"] == "BLOCKED"))
    checks.append(("url 空は BLOCKED", mod.build_plan(_args(url=""))["status"] == "BLOCKED"))
    checks.append(("委譲先は add_source_candidate", p["delegate_script"] == "scripts/add_source_candidate.py"))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
