#!/usr/bin/env python3
"""prepare_video_reference.build_plan の安全ゲート（特に download 二重ゲート）を検証する。"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/prepare_video_reference.py"


def _load():
    spec = importlib.util.spec_from_file_location("prepare_video_reference", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _args(**kw):
    base = dict(account_id="liver_manager", platform="threads", source_platform="youtube",
                video_url="https://example.com/v", source_id=None,
                apply=False, confirm_prepare=False, allow_download=False, confirm_download=False)
    base.update(kw)
    return SimpleNamespace(**base)


def main() -> int:
    mod = _load()
    checks: list[tuple[str, bool]] = []

    p = mod.build_plan(_args())
    checks.append(("既定は PLAN_ONLY", p["status"] == "PLAN_ONLY"))
    checks.append(("PLAN_ONLY は --dry-run 付き", "--dry-run" in p["delegate_argv"]))
    checks.append(("download 既定 false", p["safety"]["media_download"] is False))
    checks.append(("cloudinary upload false", p["safety"]["cloudinary_upload"] is False))
    checks.append(("ffmpeg cut false", p["safety"]["ffmpeg_cut"] is False))

    # download は二重ゲート: 片方だけでは false
    checks.append(("allow のみは download false",
                   mod.build_plan(_args(allow_download=True))["safety"]["media_download"] is False))
    checks.append(("confirm のみは download false",
                   mod.build_plan(_args(confirm_download=True))["safety"]["media_download"] is False))
    checks.append(("両方で download true",
                   mod.build_plan(_args(allow_download=True, confirm_download=True))["safety"]["media_download"] is True))

    # 実行ゲート
    p3 = mod.build_plan(_args(apply=True, confirm_prepare=True))
    checks.append(("apply+confirm は WILL_RUN", p3["status"] == "WILL_RUN"))
    checks.append(("WILL_RUN は --dry-run なし", "--dry-run" not in p3["delegate_argv"]))

    checks.append(("beauty は BLOCKED", mod.build_plan(_args(account_id="beauty_account"))["status"] == "BLOCKED"))
    checks.append(("x は BLOCKED", mod.build_plan(_args(platform="x"))["status"] == "BLOCKED"))
    checks.append(("url/source なしは BLOCKED",
                   mod.build_plan(_args(video_url=None, source_id=None))["status"] == "BLOCKED"))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
