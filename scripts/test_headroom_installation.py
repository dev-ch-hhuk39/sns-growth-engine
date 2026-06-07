"""
test_headroom_installation.py - Headroom インストール確認テスト（Phase HR-1）

headroom-ai[proxy] のインストール状態と設定ファイルの存在を確認する。

重要:
  - headroom-ai[all] がインストールされていないことを確認する（禁止）
  - requirements.txt に headroom 依存が追加されていないことを確認する
  - 実インストールは行わない（pipx / ~/.venvs/headroom は別途手動実行）

実行方法: python scripts/test_headroom_installation.py
"""
from __future__ import annotations

import os
import shutil
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# テストフレームワーク
# ============================================================

_PASS = 0
_FAIL = 0
_WARN = 0
_tests: list[tuple[str, str, str]] = []  # (name, level, msg)


def _test(name: str, fn) -> None:
    global _PASS, _FAIL
    try:
        fn()
        _PASS += 1
        _tests.append((name, "PASS", ""))
    except AssertionError as e:
        _FAIL += 1
        _tests.append((name, "FAIL", str(e)))
    except Exception as e:
        _FAIL += 1
        _tests.append((name, "FAIL", str(e)))


def _warn_test(name: str, fn) -> None:
    """WARN レベルテスト（失敗してもテスト全体は通過）。"""
    global _PASS, _WARN
    try:
        fn()
        _PASS += 1
        _tests.append((name, "PASS", ""))
    except Exception as e:
        _WARN += 1
        _tests.append((name, "WARN", str(e)))


# ============================================================
# 安全ガード: headroom-ai[all] 禁止確認
# ============================================================

print("\n=== Headroom 安全ガード ===")


def t_requirements_no_headroom():
    """requirements.txt に headroom 依存が追加されていないことを確認。"""
    req_files = [
        os.path.join(_V2_ROOT, "requirements.txt"),
        os.path.join(_V2_ROOT, "requirements-dev.txt"),
        os.path.join(_V2_ROOT, "pyproject.toml"),
    ]
    for req_file in req_files:
        if not os.path.isfile(req_file):
            continue
        with open(req_file, encoding="utf-8") as f:
            content = f.read().lower()
        assert "headroom" not in content, \
            f"headroom が {req_file} に追加されています（禁止）。pipx でのみインストールしてください。"


def t_no_headroom_all_installed():
    """headroom-ai[all] がインストールされていないことを確認（pipx 環境確認）。"""
    import subprocess
    try:
        result = subprocess.run(
            ["pipx", "list"],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout.lower()
        # headroom-all や headroom[all] のパターンを検出
        assert "headroom" not in output or "headroom-ai" not in output or "[all]" not in output, \
            "headroom-ai[all] が pipx にインストールされています（禁止）。proxy のみ許可。"
    except FileNotFoundError:
        pass  # pipx 未インストールは OK（WARN 対象）


def t_headroom_proxy_docs_exists():
    """headroom production setup ドキュメントが存在することを確認。"""
    path = os.path.join(_V2_ROOT, "docs", "headroom-production-setup.md")
    assert os.path.isfile(path), f"Headroom セットアップドキュメントが必要: {path}"


_test("requirements.txt に headroom 依存なし（禁止ガード）", t_requirements_no_headroom)
_test("headroom-ai[all] がインストールされていない（禁止ガード）", t_no_headroom_all_installed)
_test("headroom-production-setup.md ドキュメント存在", t_headroom_proxy_docs_exists)


# ============================================================
# Phase HR-1: headroom インストール状態確認（WARN 許容）
# ============================================================

print("\n=== Phase HR-1: Headroom インストール状態（WARN 許容） ===")


_HEADROOM_VENV_BIN = os.path.expanduser("~/.venvs/headroom/bin/headroom")
_HEADROOM_VENV_EXISTS = os.path.isfile(_HEADROOM_VENV_BIN)


def t_headroom_available():
    """headroom が利用可能かチェック（venv / pipx / PATH いずれか）。"""
    pipx_path = shutil.which("pipx")
    has_pipx = pipx_path is not None
    headroom_in_path = shutil.which("headroom") is not None

    status = {
        "venv (~/.venvs/headroom)": _HEADROOM_VENV_EXISTS,
        "headroom in PATH": headroom_in_path,
        "pipx": has_pipx,
    }

    assert _HEADROOM_VENV_EXISTS or headroom_in_path or has_pipx, \
        f"headroom が見つかりません。docs/headroom-production-setup.md を参照してください\n{status}"


def t_headroom_venv_version():
    """~/.venvs/headroom の headroom バージョン確認（WARN 許容）。"""
    assert _HEADROOM_VENV_EXISTS, \
        f"~/.venvs/headroom/bin/headroom が見つかりません: {_HEADROOM_VENV_BIN}"
    import subprocess
    result = subprocess.run(
        [_HEADROOM_VENV_BIN, "--version"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"headroom --version が失敗: {result.stderr}"
    assert "headroom" in result.stdout.lower(), f"version 出力が不正: {result.stdout!r}"


def t_claude_hr_wrapper_exists():
    """~/.local/bin/claude-hr が存在することを確認。"""
    claude_hr = os.path.expanduser("~/.local/bin/claude-hr")
    assert os.path.isfile(claude_hr), \
        f"claude-hr が未作成: {claude_hr}\n→ docs/headroom-production-setup.md の手順に従って作成してください"
    assert os.access(claude_hr, os.X_OK), f"claude-hr に実行権限がありません: {claude_hr}"


_test("headroom が venv / PATH / pipx のいずれかで利用可能", t_headroom_available)
_warn_test("~/.venvs/headroom バージョン確認（WARN 許容）", t_headroom_venv_version)
_test("~/.local/bin/claude-hr が存在・実行可能", t_claude_hr_wrapper_exists)


# ============================================================
# Phase HR-1: Hermes Agent 未インストール確認
# ============================================================

print("\n=== Phase HR-1: Hermes Agent 未インストール確認 ===")


def t_hermes_agent_not_installed():
    """hermes_agent が未インストールであること（意図的・まだインストール不要）。"""
    import importlib.util
    hermes_spec = importlib.util.find_spec("hermes_agent")
    assert hermes_spec is None, \
        "hermes_agent がインストールされています。まだインストール予定外です。\n" \
        "→ docs/hermes-agent-integration-plan.md を確認してください"


_warn_test("hermes_agent 未インストール（まだインストール予定外）", t_hermes_agent_not_installed)


# ============================================================
# Phase HR-1: docs ファイル確認
# ============================================================

print("\n=== Phase HR-1: docs ファイル確認 ===")


def t_headroom_setup_doc_has_proxy_instruction():
    path = os.path.join(_V2_ROOT, "docs", "headroom-production-setup.md")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "proxy" in content.lower(), "proxy インストール手順がドキュメントに必要"
    assert "[all]" in content.lower() or "禁止" in content, \
        "headroom-ai[all] の禁止事項がドキュメントに必要"


def t_hermes_integration_plan_exists():
    path = os.path.join(_V2_ROOT, "docs", "hermes-agent-integration-plan.md")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_self_improvement_architecture_exists():
    path = os.path.join(_V2_ROOT, "docs", "self-improvement-architecture.md")
    assert os.path.isfile(path), f"見つかりません: {path}"


_test("headroom-production-setup.md に proxy 手順と [all] 禁止記載", t_headroom_setup_doc_has_proxy_instruction)
_test("hermes-agent-integration-plan.md 存在", t_hermes_integration_plan_exists)
_test("self-improvement-architecture.md 存在", t_self_improvement_architecture_exists)


# ============================================================
# 結果表示
# ============================================================

print("\n" + "=" * 60)
print(f"  test_headroom_installation.py 結果: PASS={_PASS} WARN={_WARN} FAIL={_FAIL}")
print("=" * 60)

for name, level, msg in _tests:
    icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[level]
    if level == "PASS":
        print(f"  {icon} {name}")
    else:
        print(f"  {icon} {name}")
        if msg:
            print(f"         → {msg}")

if _FAIL > 0:
    sys.exit(1)
sys.exit(0)
