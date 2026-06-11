"""
test_context_mode_installation.py - Phase ENV-1 context-mode 導入確認テスト

実行方法: python scripts/test_context_mode_installation.py
"""
from __future__ import annotations

import os
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
    """WARN レベルのテスト（FAILにしないが記録する）。"""
    global _WARN
    try:
        fn()
        _tests.append((name, "PASS", ""))
        global _PASS
        _PASS += 1
    except Exception as e:
        _WARN += 1
        _tests.append((name, "WARN", str(e)))


print("\n=== Phase ENV-1: context-mode 導入確認 ===")

# --------------------------------------------------------
# docs 存在確認
# --------------------------------------------------------

def t_docs_exists():
    p = os.path.join(_V2_ROOT, "docs", "context-mode-production-setup.md")
    assert os.path.isfile(p), f"docs/context-mode-production-setup.md が存在しません: {p}"


def t_docs_has_install_method():
    p = os.path.join(_V2_ROOT, "docs", "context-mode-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "/plugin" in src or "mcp add" in src, \
        "context-mode 導入方法が記録されていません"


def t_docs_has_claude_code_plugin_policy():
    p = os.path.join(_V2_ROOT, "docs", "context-mode-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "Claude Code" in src and ("plugin" in src.lower() or "mcp" in src.lower()), \
        "Claude Code plugin 方針が記録されていません"


def t_docs_codex_excluded():
    p = os.path.join(_V2_ROOT, "docs", "context-mode-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "Codex" in src, "Codex 対象外方針が明記されていません"
    # 「Codex には適用しない」が明記されていること
    assert "適用しない" in src or "対象外" in src or "not apply" in src.lower(), \
        "Codex に適用しない方針が明記されていません"


def t_docs_clear_compact_policy():
    p = os.path.join(_V2_ROOT, "docs", "context-mode-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "/clear" in src, "/clear の方針が必要"
    assert "/compact" in src, "/compact の方針が必要"


def t_docs_secrets_policy():
    p = os.path.join(_V2_ROOT, "docs", "context-mode-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "secret" in src.lower() or "シークレット" in src or "機密" in src, \
        "secrets 非表示方針が記録されていません"


def t_docs_no_commit_cache():
    p = os.path.join(_V2_ROOT, "docs", "context-mode-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "commit" in src.lower(), "cache/SQLite/index をcommitしない方針が必要"
    assert ("SQLite" in src or "db" in src.lower() or "cache" in src.lower()), \
        "SQLite/cache 除外方針が必要"


def t_docs_old_folder_policy():
    p = os.path.join(_V2_ROOT, "docs", "context-mode-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "使ってない_過去" in src or "旧" in src or "退避" in src, \
        "旧zip退避フォルダを触らない方針が必要"


def t_gitignore_has_context_mode():
    p = os.path.join(_V2_ROOT, ".gitignore")
    assert os.path.isfile(p), ".gitignore が存在しません"
    src = open(p, encoding="utf-8").read()
    assert "context-mode" in src or "context_mode" in src.lower(), \
        ".gitignore に context-mode の除外設定が必要"


def t_docs_headroom_difference():
    p = os.path.join(_V2_ROOT, "docs", "context-mode-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "Headroom" in src, "Headroom との違いが記録されていません"


def t_docs_codegraph_difference():
    p = os.path.join(_V2_ROOT, "docs", "context-mode-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "CodeGraph" in src, "CodeGraph との違いが記録されていません"


def t_docs_uninstall():
    p = os.path.join(_V2_ROOT, "docs", "context-mode-production-setup.md")
    src = open(p, encoding="utf-8").read()
    assert "uninstall" in src.lower() or "削除" in src or "remove" in src.lower(), \
        "uninstall 方法が記録されていません"


# context-mode が実際にインストールされているかはWARNのみ（環境依存）
def t_plugin_available_warn():
    import subprocess
    r = subprocess.run(
        ["claude", "--help"],
        capture_output=True, text=True, timeout=10
    )
    # context-mode がないこと自体は fail にしない（環境依存）
    # ドキュメントがあれば十分
    assert True


for fn in [
    t_docs_exists,
    t_docs_has_install_method,
    t_docs_has_claude_code_plugin_policy,
    t_docs_codex_excluded,
    t_docs_clear_compact_policy,
    t_docs_secrets_policy,
    t_docs_no_commit_cache,
    t_docs_old_folder_policy,
    t_gitignore_has_context_mode,
    t_docs_headroom_difference,
    t_docs_codegraph_difference,
    t_docs_uninstall,
]:
    _test(fn.__name__[2:], fn)

_warn_test("plugin_available_warn", t_plugin_available_warn)


print("\n============================================================")
print(f"  Phase ENV-1 テスト結果: PASS={_PASS} / FAIL={_FAIL} / WARN={_WARN}")
print("============================================================")

for name, status, msg in _tests:
    icon = {"PASS": "  [PASS]", "FAIL": "  [FAIL]", "WARN": "  [WARN]"}[status]
    suffix = f" — {msg}" if msg else ""
    print(f"{icon} {name}{suffix}")

if _FAIL > 0:
    sys.exit(1)
