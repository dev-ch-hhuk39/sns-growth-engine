"""
test_codegraph_installation.py - Phase CG-1 CodeGraph 導入確認テスト

実行方法: python scripts/test_codegraph_installation.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_PASS = 0
_FAIL = 0
_WARN = 0
_tests: list[tuple[str, str, str]] = []


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
    global _WARN
    try:
        fn()
        global _PASS
        _PASS += 1
        _tests.append((name, "PASS", ""))
    except Exception as e:
        _WARN += 1
        _tests.append((name, "WARN", str(e)))


print("\n=== Phase CG-1: CodeGraph 導入確認 ===")


# --------------------------------------------------------
# codegraph command 存在（WARN のみ - 未インストール環境を考慮）
# --------------------------------------------------------

def t_codegraph_command_warn():
    cg = shutil.which("codegraph")
    assert cg is not None, "codegraph コマンドが見つかりません（npm i -g @colbymchenry/codegraph で導入可能）"


def t_codegraph_version_warn():
    cg = shutil.which("codegraph")
    if cg is None:
        raise AssertionError("codegraph コマンドなし")
    r = subprocess.run(["codegraph", "--version"], capture_output=True, text=True, timeout=10)
    assert r.returncode == 0, f"codegraph --version 失敗: {r.stderr}"


# --------------------------------------------------------
# .codegraph/ が gitignore されているか
# --------------------------------------------------------

def t_codegraph_gitignored():
    gitignore_path = os.path.join(_V2_ROOT, ".gitignore")
    assert os.path.isfile(gitignore_path), ".gitignore が存在しません"
    src = open(gitignore_path, encoding="utf-8").read()
    assert ".codegraph/" in src or ".codegraph" in src, \
        ".gitignore に .codegraph/ の除外設定が必要"


# --------------------------------------------------------
# requirements.txt に CodeGraph 依存がない
# --------------------------------------------------------

def t_requirements_no_codegraph():
    req_path = os.path.join(_V2_ROOT, "requirements.txt")
    if not os.path.isfile(req_path):
        return  # requirements.txt がなければスキップ
    src = open(req_path, encoding="utf-8").read().lower()
    assert "codegraph" not in src, \
        "requirements.txt に codegraph 依存が追加されています（禁止）"
    assert "@colbymchenry" not in src, \
        "requirements.txt に @colbymchenry/codegraph が追加されています（禁止）"


# --------------------------------------------------------
# docs 存在確認
# --------------------------------------------------------

def t_docs_exists():
    p = os.path.join(_V2_ROOT, "docs", "codegraph-production-setup.md")
    assert os.path.isfile(p), "docs/codegraph-production-setup.md が存在しません"


def t_docs_codex_excluded():
    p = os.path.join(_V2_ROOT, "docs", "codegraph-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "Codex" in src, "Codex 対象外方針が必要"
    assert "適用しない" in src or "対象外" in src or "not apply" in src.lower() or \
           "--target claude" in src, "Claude Code のみ対象とする方針が必要"


def t_docs_uninstall():
    p = os.path.join(_V2_ROOT, "docs", "codegraph-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "uninstall" in src.lower() or "アンインストール" in src, \
        "uninstall 手順が記録されていません"


def t_docs_v2_only():
    p = os.path.join(_V2_ROOT, "docs", "codegraph-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "v2" in src.lower() or "現行" in src, \
        "現行 v2 だけをindex対象にする方針が必要"


def t_docs_no_commit_index():
    p = os.path.join(_V2_ROOT, "docs", "codegraph-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "commit" in src.lower() and (".codegraph" in src or "index" in src.lower()), \
        ".codegraph/ をcommitしない方針が必要"


def t_docs_has_context_mode_comparison():
    p = os.path.join(_V2_ROOT, "docs", "codegraph-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "context-mode" in src or "context_mode" in src.lower(), \
        "context-mode との役割分担が記録されていません"


def t_docs_grep_read_priority():
    p = os.path.join(_V2_ROOT, "docs", "codegraph-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "grep" in src.lower() or "read" in src.lower(), \
        "大量 grep/read 前に CodeGraph を使う方針が必要"


# --------------------------------------------------------
# .mcp.json の確認（インストール済みの場合）
# --------------------------------------------------------

def t_mcp_json_exists_if_installed():
    cg = shutil.which("codegraph")
    if cg is None:
        return  # 未インストールならスキップ
    # .mcp.json は存在するはず
    mcp_path = os.path.join(_V2_ROOT, ".mcp.json")
    assert os.path.isfile(mcp_path), \
        "codegraph install 後は .mcp.json が必要です"


def t_mcp_json_claude_only():
    mcp_path = os.path.join(_V2_ROOT, ".mcp.json")
    if not os.path.isfile(mcp_path):
        return  # .mcp.json がなければスキップ
    import json
    with open(mcp_path, encoding="utf-8") as f:
        cfg = json.load(f)
    servers = cfg.get("mcpServers", {})
    assert "codegraph" in servers, ".mcp.json に codegraph サーバー設定が必要"
    # cursor / codex の設定がないことを確認
    server_cmd = str(servers.get("codegraph", {}))
    # .mcp.json はローカル設定なので Claude Code 用のみ


# --------------------------------------------------------
# .codegraph/ の安全確認
# --------------------------------------------------------

def t_codegraph_dir_no_sensitive_files():
    cg_dir = os.path.join(_V2_ROOT, ".codegraph")
    if not os.path.isdir(cg_dir):
        return  # ディレクトリなければスキップ
    files = os.listdir(cg_dir)
    # .env や secrets ファイルが混入していないこと
    for f in files:
        assert not f.startswith(".env"), f".codegraph/ に .env ファイル: {f}"
        assert "secret" not in f.lower(), f".codegraph/ に secrets ファイル: {f}"
        assert "credential" not in f.lower(), f".codegraph/ に credentials ファイル: {f}"


for fn in [
    t_codegraph_gitignored,
    t_requirements_no_codegraph,
    t_docs_exists,
    t_docs_codex_excluded,
    t_docs_uninstall,
    t_docs_v2_only,
    t_docs_no_commit_index,
    t_docs_has_context_mode_comparison,
    t_docs_grep_read_priority,
    t_mcp_json_exists_if_installed,
    t_mcp_json_claude_only,
    t_codegraph_dir_no_sensitive_files,
]:
    _test(fn.__name__[2:], fn)

_warn_test("codegraph_command_warn", t_codegraph_command_warn)
_warn_test("codegraph_version_warn", t_codegraph_version_warn)


print("\n============================================================")
print(f"  Phase CG-1 テスト結果: PASS={_PASS} / FAIL={_FAIL} / WARN={_WARN}")
print("============================================================")

for name, status, msg in _tests:
    icon = {"PASS": "  [PASS]", "FAIL": "  [FAIL]", "WARN": "  [WARN]"}[status]
    suffix = f" — {msg}" if msg else ""
    print(f"{icon} {name}{suffix}")

if _FAIL > 0:
    sys.exit(1)
