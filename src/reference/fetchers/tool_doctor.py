#!/usr/bin/env python3
"""tool_doctor.py - Source Fetcher ツール導入状況チェック"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field


@dataclass
class ToolCheckResult:
    name: str
    installed: bool
    version: str | None = None
    error: str | None = None
    required_for: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "OK" if self.installed else "NOT_INSTALLED"


def _run(cmd: list[str]) -> tuple[bool, str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return out.returncode == 0, (out.stdout.strip() or out.stderr.strip())
    except FileNotFoundError:
        return False, "command not found"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


def check_yt_dlp() -> ToolCheckResult:
    ok, ver = _run(["yt-dlp", "--version"])
    return ToolCheckResult(
        name="yt-dlp",
        installed=ok,
        version=ver if ok else None,
        error=None if ok else ver,
        required_for=["yt_dlp", "tiktok_to_ytdlp"],
    )


def check_ffmpeg() -> ToolCheckResult:
    ok, out = _run(["ffmpeg", "-version"])
    ver = out.split("\n")[0] if ok else None
    return ToolCheckResult(
        name="ffmpeg",
        installed=ok,
        version=ver,
        error=None if ok else out,
        required_for=["clip_cut", "audio_extract"],
    )


def check_youtube_transcript_api() -> ToolCheckResult:
    try:
        import youtube_transcript_api  # noqa: F401
        ver = getattr(youtube_transcript_api, "__version__", "installed")
        return ToolCheckResult(
            name="youtube-transcript-api",
            installed=True,
            version=ver,
            required_for=["youtube_transcript"],
        )
    except ImportError as e:
        return ToolCheckResult(
            name="youtube-transcript-api",
            installed=False,
            error=str(e),
            required_for=["youtube_transcript"],
        )


def check_python_version() -> ToolCheckResult:
    ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 9)
    return ToolCheckResult(
        name="python",
        installed=ok,
        version=ver,
        error=None if ok else f"Python 3.9+ required, got {ver}",
        required_for=["all"],
    )


ALL_CHECKS = [
    check_python_version,
    check_yt_dlp,
    check_ffmpeg,
    check_youtube_transcript_api,
]


def run_all_checks() -> list[ToolCheckResult]:
    return [fn() for fn in ALL_CHECKS]


def print_report(results: list[ToolCheckResult]) -> int:
    """ツール確認結果を表示。NOT_INSTALLEDがあっても終了コード0（WARN扱い）"""
    not_installed = [r for r in results if not r.installed]
    ok_count = len(results) - len(not_installed)

    print(f"\n=== Source Fetcher Tool Doctor ===")
    for r in results:
        icon = "✓" if r.installed else "✗"
        ver_str = f" ({r.version})" if r.version else ""
        adapters = ", ".join(r.required_for) if r.required_for else ""
        print(f"  {icon} [{r.status}] {r.name}{ver_str}  → {adapters}")
        if r.error:
            print(f"       Error: {r.error}")

    print(f"\n  {ok_count} OK / {len(not_installed)} NOT_INSTALLED / {len(results)} total")

    if not_installed:
        print("\n  [WARN] 以下のツールが未導入です（fetch adapter が NOT_INSTALLED を返します）:")
        for r in not_installed:
            print(f"    - {r.name}  (required for: {', '.join(r.required_for)})")
        print("  docs/source-fetcher-installation.md を参照してください。")
    else:
        print("\n  [OK] 全ツールが導入済みです。")

    return 0
