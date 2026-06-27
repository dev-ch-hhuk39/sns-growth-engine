#!/usr/bin/env python3
"""collect_reference_posts.build_plan の安全ゲートを検証する（委譲先は実行しない）。"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/collect_reference_posts.py"


def _load():
    spec = importlib.util.spec_from_file_location("collect_reference_posts", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _args(**kw):
    base = dict(account_id="night_scout", source_platform="threads", source_handle=None,
                input_json=None, top_n=10, apply=False, confirm_collect=False)
    base.update(kw)
    return SimpleNamespace(**base)


def main() -> int:
    mod = _load()
    checks: list[tuple[str, bool]] = []

    p = mod.build_plan(_args())
    checks.append(("既定は PLAN_ONLY", p["status"] == "PLAN_ONLY"))
    checks.append(("既定で --use-sheets なし", "--use-sheets" not in p["delegate_argv"]))
    checks.append(("実 X API 起動しない", "--use-x-api" not in p["delegate_argv"]))
    checks.append(("media download false", p["safety"]["media_download"] is False))

    # apply のみ（confirm なし）→ 書き込まない
    p2 = mod.build_plan(_args(apply=True))
    checks.append(("apply のみは PLAN_ONLY", p2["status"] == "PLAN_ONLY"))

    # apply + confirm → 書き込み
    p3 = mod.build_plan(_args(apply=True, confirm_collect=True))
    checks.append(("apply+confirm は WILL_WRITE", p3["status"] == "WILL_WRITE"))
    checks.append(("WILL_WRITE で --use-sheets 付与", "--use-sheets" in p3["delegate_argv"]))

    checks.append(("beauty は BLOCKED", mod.build_plan(_args(account_id="beauty_account"))["status"] == "BLOCKED"))
    checks.append(("未対応 source-platform は BLOCKED",
                   mod.build_plan(_args(source_platform="instagram"))["status"] == "BLOCKED"))
    checks.append(("委譲先は collect_source_account_posts",
                   p["delegate_script"] == "scripts/collect_source_account_posts.py"))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
