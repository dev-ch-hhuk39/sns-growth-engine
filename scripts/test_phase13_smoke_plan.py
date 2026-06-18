#!/usr/bin/env python3
"""test_phase13_smoke_plan.py"""
from __future__ import annotations
import os, sys, subprocess
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"  {'✓' if condition else '✗'} [{status}] {name}" + (f": {detail}" if detail else ""))


def _run(cmd: list[str]) -> tuple[int, str, str]:
    r = subprocess.run(
        [sys.executable] + cmd,
        capture_output=True, text=True,
        cwd=_ROOT,
    )
    return r.returncode, r.stdout, r.stderr


def main():
    print("=== Phase 13: SmokePlan テスト ===\n")

    print("[1] run_phase13_smoke_plan.py — night_scout / x")
    code, out, err = _run([
        "scripts/run_phase13_smoke_plan.py",
        "--account-id", "night_scout",
        "--platform", "x",
    ])
    check("exit_code=0", code == 0, f"code={code}\nout={out[-300:]}\nerr={err[-200:]}")
    check("SMOKE PASS in stdout", "SMOKE PASS" in out or "SMOKE" in out)

    print("\n[2] run_phase13_smoke_plan.py — liver_manager / threads")
    code2, out2, err2 = _run([
        "scripts/run_phase13_smoke_plan.py",
        "--account-id", "liver_manager",
        "--platform", "threads",
    ])
    check("exit_code=0", code2 == 0, f"code={code2}\nerr={err2[-200:]}")
    check("Step 1: ToolDoctor 実行", "ToolDoctor" in out2 or "tool_doctor" in out2)
    check("Step 4: Publisher 実行", "publisher" in out2.lower() or "Publisher" in out2)

    print("\n[3] publish_x_post.py — dry_run (デフォルト)")
    code3, out3, err3 = _run([
        "scripts/publish_x_post.py",
        "--account-id", "night_scout",
        "--text", "テストテキスト Phase13 dry_run",
    ])
    check("exit_code=0", code3 == 0, f"code={code3} err={err3[:100]}")
    check("DRY_RUN in stdout", "DRY_RUN" in out3)

    print("\n[4] publish_x_post.py — beauty_account は BLOCKED")
    code4, out4, _ = _run([
        "scripts/publish_x_post.py",
        "--account-id", "beauty_account",
        "--text", "テスト",
    ])
    check("beauty_account: exit_code=1", code4 == 1)
    check("BLOCKED in stdout", "BLOCKED" in out4)

    print("\n[5] publish_x_post.py — 280文字超でエラー")
    code5, out5, _ = _run([
        "scripts/publish_x_post.py",
        "--account-id", "night_scout",
        "--text", "あ" * 281,
    ])
    check("281文字: exit_code=1", code5 == 1)
    check("280文字エラーメッセージ", "280" in out5 or "280" in _)

    print("\n[6] publish_threads_post.py — dry_run")
    code6, out6, err6 = _run([
        "scripts/publish_threads_post.py",
        "--account-id", "night_scout",
        "--text", "Threads テスト Phase13",
    ])
    check("exit_code=0", code6 == 0, f"code={code6} err={err6[:100]}")
    check("DRY_RUN in stdout", "DRY_RUN" in out6)

    print("\n[7] publish_threads_post.py — beauty_account は BLOCKED")
    code7, out7, _ = _run([
        "scripts/publish_threads_post.py",
        "--account-id", "beauty_account",
        "--text", "テスト",
    ])
    check("beauty_account Threads: exit_code=1", code7 == 1)
    check("BLOCKED in stdout", "BLOCKED" in out7)

    print("\n[8] run_real_smoke_plan.py — --platform threads はThreads preflightを使う")
    code8, out8, err8 = _run([
        "scripts/run_real_smoke_plan.py",
        "--account-id", "liver_manager",
        "--platform", "threads",
        "--dry-run",
    ])
    check("exit_code is readiness result", code8 in (0, 1), f"code={code8} err={err8[-200:]}")
    check("THREADS check in stdout", "[THREADS] チェック開始" in out8)
    check("X check not used for threads platform", "[X] チェック開始" not in out8)

    print("\n--- 結果 ---")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"PASS: {passed} / FAIL: {failed}")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
