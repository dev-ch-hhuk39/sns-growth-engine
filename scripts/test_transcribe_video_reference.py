#!/usr/bin/env python3
"""transcribe_video_reference.build_plan の実 API 二重ゲートを検証する。"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/transcribe_video_reference.py"


def _load():
    spec = importlib.util.spec_from_file_location("transcribe_video_reference", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _args(**kw):
    base = dict(account_id="liver_manager", limit=10, apply=False,
                confirm_transcribe=False, allow_real_transcription=False)
    base.update(kw)
    return SimpleNamespace(**base)


def main() -> int:
    mod = _load()
    checks: list[tuple[str, bool]] = []
    ENV_OFF = {"ALLOW_TRANSCRIPTION_API": "false"}
    ENV_ON = {"ALLOW_TRANSCRIPTION_API": "true"}

    p = mod.build_plan(_args(), env=ENV_OFF)
    checks.append(("既定は PLAN_ONLY", p["status"] == "PLAN_ONLY"))
    checks.append(("既定は mock-sheets", "--mock-sheets" in p["delegate_argv"]))
    checks.append(("既定で実 API なし", p["safety"]["real_transcription_api"] is False))
    checks.append(("既定で --allow-real-transcription なし", "--allow-real-transcription" not in p["delegate_argv"]))

    # フラグありでも env off なら実 API false
    p_flag = mod.build_plan(_args(allow_real_transcription=True), env=ENV_OFF)
    checks.append(("flag のみ(env off)は実 API false", p_flag["safety"]["real_transcription_api"] is False))

    # env on でもフラグなしなら false
    p_env = mod.build_plan(_args(), env=ENV_ON)
    checks.append(("env on のみは実 API false", p_env["safety"]["real_transcription_api"] is False))

    # 二重ゲート成立 + 実行
    p_real = mod.build_plan(_args(apply=True, confirm_transcribe=True, allow_real_transcription=True), env=ENV_ON)
    checks.append(("二重ゲート+実行で実 API true", p_real["safety"]["real_transcription_api"] is True))
    checks.append(("実 API 実行で --allow-real-transcription 付与",
                   "--allow-real-transcription" in p_real["delegate_argv"]))

    # 実行だが実 API なし → mock-sheets で書き込み
    p_mock_write = mod.build_plan(_args(apply=True, confirm_transcribe=True), env=ENV_OFF)
    checks.append(("実行(実APIなし)は mock-sheets 書き込み",
                   "--mock-sheets" in p_mock_write["delegate_argv"]
                   and "--allow-real-transcription" not in p_mock_write["delegate_argv"]))

    checks.append(("beauty は BLOCKED", mod.build_plan(_args(account_id="beauty_account"), env=ENV_OFF)["status"] == "BLOCKED"))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
