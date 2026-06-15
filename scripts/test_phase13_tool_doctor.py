#!/usr/bin/env python3
"""test_phase13_tool_doctor.py"""
from __future__ import annotations
import os, sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"  {'✓' if condition else '✗'} [{status}] {name}" + (f": {detail}" if detail else ""))


def main():
    print("=== Phase 13: ToolDoctor テスト ===\n")

    print("[1] Import")
    try:
        from src.reference.fetchers.tool_doctor import (
            ToolCheckResult,
            check_yt_dlp,
            check_ffmpeg,
            check_youtube_transcript_api,
            check_python_version,
            run_all_checks,
            print_report,
        )
        check("import OK", True)
    except Exception as e:
        check("import", False, str(e))
        sys.exit(1)

    print("\n[2] ToolCheckResult dataclass")
    ok = ToolCheckResult(name="test", installed=True, version="1.0")
    check("status=OK when installed", ok.status == "OK")
    ng = ToolCheckResult(name="test", installed=False, error="not found")
    check("status=NOT_INSTALLED when not installed", ng.status == "NOT_INSTALLED")
    check("required_for default empty list", ok.required_for == [])

    print("\n[3] check_python_version")
    r = check_python_version()
    check("returns ToolCheckResult", isinstance(r, ToolCheckResult))
    check("name=python", r.name == "python")
    check("installed=True (python is running)", r.installed is True)
    check("version not None", r.version is not None)

    print("\n[4] check_yt_dlp")
    r = check_yt_dlp()
    check("returns ToolCheckResult", isinstance(r, ToolCheckResult))
    check("name=yt-dlp", r.name == "yt-dlp")
    check("installed is bool", isinstance(r.installed, bool))
    check("status is OK or NOT_INSTALLED", r.status in ("OK", "NOT_INSTALLED"))
    if r.installed:
        check("version not None when installed", r.version is not None)

    print("\n[5] check_ffmpeg")
    r = check_ffmpeg()
    check("returns ToolCheckResult", isinstance(r, ToolCheckResult))
    check("name=ffmpeg", r.name == "ffmpeg")
    check("installed is bool", isinstance(r.installed, bool))
    check("status in valid values", r.status in ("OK", "NOT_INSTALLED"))

    print("\n[6] check_youtube_transcript_api")
    r = check_youtube_transcript_api()
    check("returns ToolCheckResult", isinstance(r, ToolCheckResult))
    check("name=youtube-transcript-api", r.name == "youtube-transcript-api")
    check("status in valid values", r.status in ("OK", "NOT_INSTALLED"))

    print("\n[7] run_all_checks")
    all_results = run_all_checks()
    check("returns list", isinstance(all_results, list))
    check("4件以上", len(all_results) >= 4)
    names = [r.name for r in all_results]
    check("python included", "python" in names)
    check("yt-dlp included", "yt-dlp" in names)
    check("ffmpeg included", "ffmpeg" in names)
    check("youtube-transcript-api included", "youtube-transcript-api" in names)

    print("\n[8] print_report (NOT_INSTALLED は WARN=0で終了)")
    exit_code = print_report(all_results)
    check("exit_code is int", isinstance(exit_code, int))
    check("exit_code == 0 (NOT_INSTALLED is WARN not FAIL)", exit_code == 0)

    print("\n[9] print_report with all-installed mock")
    mock_ok = [
        ToolCheckResult(name="yt_dlp", installed=True, version="2025.01.01"),
        ToolCheckResult(name="ffmpeg", installed=True, version="6.0"),
        ToolCheckResult(name="youtube_transcript_api", installed=True, version="0.6.2"),
        ToolCheckResult(name="python", installed=True, version="3.11.0"),
    ]
    exit_code_ok = print_report(mock_ok)
    check("exit_code == 0 when all OK", exit_code_ok == 0)

    print("\n--- 結果 ---")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"PASS: {passed} / FAIL: {failed}")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
