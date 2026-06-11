"""
test_development_environment_strategy.py - Phase ENV-2 開発環境戦略テスト

実行方法: python scripts/test_development_environment_strategy.py
"""
from __future__ import annotations

import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_PASS = 0
_FAIL = 0
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


print("\n=== Phase ENV-2: 開発環境戦略確認 ===")


# --------------------------------------------------------
# development-environment-strategy.md
# --------------------------------------------------------

def t_strategy_doc_exists():
    p = os.path.join(_V2_ROOT, "docs", "development-environment-strategy.md")
    assert os.path.isfile(p), "docs/development-environment-strategy.md が存在しません"


def t_strategy_has_context_mode():
    p = os.path.join(_V2_ROOT, "docs", "development-environment-strategy.md")
    src = open(p, encoding="utf-8").read()
    assert "context-mode" in src or "context_mode" in src.lower(), \
        "context-mode の役割が整理されていません"


def t_strategy_has_codegraph():
    p = os.path.join(_V2_ROOT, "docs", "development-environment-strategy.md")
    src = open(p, encoding="utf-8").read()
    assert "CodeGraph" in src, "CodeGraph の役割が整理されていません"


def t_strategy_has_headroom():
    p = os.path.join(_V2_ROOT, "docs", "development-environment-strategy.md")
    src = open(p, encoding="utf-8").read()
    assert "Headroom" in src, "Headroom の役割が整理されていません"


def t_strategy_has_hermes():
    p = os.path.join(_V2_ROOT, "docs", "development-environment-strategy.md")
    src = open(p, encoding="utf-8").read()
    assert "Hermes" in src, "Hermes Agent の役割が整理されていません"


def t_strategy_recommends_claude_context_codegraph():
    p = os.path.join(_V2_ROOT, "docs", "development-environment-strategy.md")
    src = open(p, encoding="utf-8").read()
    # 推奨運用が通常 Claude Code + context-mode + CodeGraph であること
    assert "claude" in src.lower(), "claude コマンドの推奨起動方法が必要"
    assert "context-mode" in src or "context_mode" in src.lower(), \
        "context-mode が推奨運用に含まれていません"
    assert "CodeGraph" in src, "CodeGraph が推奨運用に含まれていません"


def t_strategy_headroom_not_deleted():
    p = os.path.join(_V2_ROOT, "docs", "development-environment-strategy.md")
    src = open(p, encoding="utf-8").read()
    # 削除対象ではないことが明記されていること
    assert "削除しない" in src or "保持" in src or "補助" in src or "保留" in src, \
        "Headroom が削除対象ではないことが明記されていません"


def t_strategy_headroom_is_auxiliary():
    p = os.path.join(_V2_ROOT, "docs", "development-environment-strategy.md")
    src = open(p, encoding="utf-8").read()
    # 補助・検証枠扱いであること
    assert "補助" in src or "追加検証" in src or "optional" in src.lower(), \
        "Headroom が補助扱いであることが明記されていません"


def t_strategy_codex_excluded():
    p = os.path.join(_V2_ROOT, "docs", "development-environment-strategy.md")
    src = open(p, encoding="utf-8").read()
    assert "Codex" in src, "Codex に関する方針が必要"
    assert "使わない" in src or "対象外" in src or "適用しない" in src or "not apply" in src.lower(), \
        "Codex を使わない方針が明記されていません"


def t_strategy_has_compact_clear():
    p = os.path.join(_V2_ROOT, "docs", "development-environment-strategy.md")
    src = open(p, encoding="utf-8").read()
    assert "/compact" in src, "/compact の使い分けが必要"
    assert "/clear" in src, "/clear の使い分けが必要"


def t_strategy_old_folder_policy():
    p = os.path.join(_V2_ROOT, "docs", "development-environment-strategy.md")
    src = open(p, encoding="utf-8").read()
    assert "使ってない_過去" in src or "旧" in src or "退避" in src, \
        "旧zip退避フォルダを触らない方針が必要"


def t_strategy_has_tool_reduction_table():
    p = os.path.join(_V2_ROOT, "docs", "development-environment-strategy.md")
    src = open(p, encoding="utf-8").read()
    # どのツールが何を削減するか
    assert "削減" in src or "reduce" in src.lower() or "context" in src.lower(), \
        "ツールが何を削減するかの説明が必要"


# --------------------------------------------------------
# headroom-production-setup.md が補助扱いに更新されているか
# --------------------------------------------------------

def t_headroom_doc_has_auxiliary_status():
    p = os.path.join(_V2_ROOT, "docs", "headroom-production-setup.md")
    assert os.path.isfile(p), "docs/headroom-production-setup.md が存在しません"
    src = open(p, encoding="utf-8").read()
    assert "補助" in src or "追加検証" in src or "optional" in src.lower(), \
        "headroom-production-setup.md に補助扱いの記載が必要"


def t_headroom_doc_not_deleted():
    p = os.path.join(_V2_ROOT, "docs", "headroom-production-setup.md")
    assert os.path.isfile(p), "headroom-production-setup.md が削除されています（削除禁止）"


# --------------------------------------------------------
# context-mode-production-setup.md / codegraph-production-setup.md 存在
# --------------------------------------------------------

def t_context_mode_doc_exists():
    p = os.path.join(_V2_ROOT, "docs", "context-mode-production-setup.md")
    assert os.path.isfile(p), "docs/context-mode-production-setup.md が存在しません"


def t_codegraph_doc_exists():
    p = os.path.join(_V2_ROOT, "docs", "codegraph-production-setup.md")
    assert os.path.isfile(p), "docs/codegraph-production-setup.md が存在しません"


# --------------------------------------------------------
# Hermes Agent 未インストール確認
# --------------------------------------------------------

def t_hermes_not_installed():
    import shutil
    hermes = shutil.which("hermes") or shutil.which("hermes-agent")
    assert hermes is None, "hermes_agent がインストールされています（禁止）"


def t_hermes_agent_not_in_requirements():
    req_path = os.path.join(_V2_ROOT, "requirements.txt")
    if not os.path.isfile(req_path):
        return
    src = open(req_path, encoding="utf-8").read().lower()
    assert "hermes" not in src or "hermes-agent" not in src, \
        "requirements.txt に hermes-agent が追加されています（禁止）"


for fn in [
    t_strategy_doc_exists,
    t_strategy_has_context_mode,
    t_strategy_has_codegraph,
    t_strategy_has_headroom,
    t_strategy_has_hermes,
    t_strategy_recommends_claude_context_codegraph,
    t_strategy_headroom_not_deleted,
    t_strategy_headroom_is_auxiliary,
    t_strategy_codex_excluded,
    t_strategy_has_compact_clear,
    t_strategy_old_folder_policy,
    t_strategy_has_tool_reduction_table,
    t_headroom_doc_has_auxiliary_status,
    t_headroom_doc_not_deleted,
    t_context_mode_doc_exists,
    t_codegraph_doc_exists,
    t_hermes_not_installed,
    t_hermes_agent_not_in_requirements,
]:
    _test(fn.__name__[2:], fn)


print("\n============================================================")
print(f"  Phase ENV-2 テスト結果: PASS={_PASS} / FAIL={_FAIL}")
print("============================================================")

for name, status, msg in _tests:
    icon = {"PASS": "  [PASS]", "FAIL": "  [FAIL]"}[status]
    suffix = f" — {msg}" if msg else ""
    print(f"{icon} {name}{suffix}")

if _FAIL > 0:
    sys.exit(1)
