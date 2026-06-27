#!/usr/bin/env python3
"""generate_clip_candidates.build_plan の安全ゲート（ffmpeg cut 禁止）を検証する。"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/generate_clip_candidates.py"


def _load():
    spec = importlib.util.spec_from_file_location("generate_clip_candidates", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _args(**kw):
    base = dict(account_id="liver_manager", limit=5, n_candidates=6,
                transcript_status="done", apply=False, confirm_generate=False, cut=False)
    base.update(kw)
    return SimpleNamespace(**base)


def main() -> int:
    mod = _load()
    checks: list[tuple[str, bool]] = []

    p = mod.build_plan(_args())
    checks.append(("既定は PLAN_ONLY", p["status"] == "PLAN_ONLY"))
    checks.append(("既定で --use-sheets なし", "--use-sheets" not in p["delegate_argv"]))
    checks.append(("ffmpeg cut false", p["safety"]["ffmpeg_cut"] is False))
    checks.append(("cut フラグを委譲先に渡さない",
                   "--cut" not in p["delegate_argv"] and "--confirm-cut" not in p["delegate_argv"]))

    p3 = mod.build_plan(_args(apply=True, confirm_generate=True))
    checks.append(("apply+confirm は WILL_WRITE", p3["status"] == "WILL_WRITE"))
    checks.append(("WILL_WRITE で --use-sheets 付与", "--use-sheets" in p3["delegate_argv"]))

    checks.append(("--cut 指定は BLOCKED", mod.build_plan(_args(cut=True))["status"] == "BLOCKED"))
    checks.append(("beauty は BLOCKED", mod.build_plan(_args(account_id="beauty_account"))["status"] == "BLOCKED"))
    checks.append(("委譲先は analyze_video_clips", p["delegate_script"] == "scripts/analyze_video_clips.py"))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
