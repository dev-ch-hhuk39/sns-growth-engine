"""
test_phase42_45_learning_workflow.py - Phase 4.2〜4.5 学習ワークフロー テスト

Phase 4.2: 改善提案レビューフロー（フィルター・禁止パターン検出）
Phase 4.3: Hermes向けexport/import（4ファイル出力・forbidden conflict検出）
Phase 4.4: 週次改善レポート生成
Phase 4.5: 学習ルール有効化安全化（--confirm-activate必須・禁止パターンブロック）

実行方法: python scripts/test_phase42_45_learning_workflow.py
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

# ============================================================
# テストフレームワーク
# ============================================================

_PASS = 0
_FAIL = 0
_tests: list[tuple[str, bool, str]] = []


def _test(name: str, fn) -> None:
    global _PASS, _FAIL
    try:
        fn()
        _PASS += 1
        _tests.append((name, True, ""))
    except Exception as e:
        _FAIL += 1
        _tests.append((name, False, str(e)))


# ============================================================
# Phase 4.2: review_improvement_suggestions
# ============================================================

print("\n=== Phase 4.2: review_improvement_suggestions ===")


def t_review_script_exists():
    path = os.path.join(_V2_ROOT, "scripts", "review_improvement_suggestions.py")
    assert os.path.isfile(path), f"スクリプトが見つかりません: {path}"


def t_review_script_has_valid_statuses():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "review_improvement_suggestions",
        os.path.join(_V2_ROOT, "scripts", "review_improvement_suggestions.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    statuses = mod.VALID_STATUSES
    required = {"WAITING_REVIEW", "APPROVED", "REJECTED", "IMPORTED", "CONVERTED_TO_RULE"}
    missing = required - statuses
    assert not missing, f"VALID_STATUSES に不足: {missing}"


def t_review_script_has_forbidden_conflict_fn():
    spec = importlib.util.spec_from_file_location(
        "review_improvement_suggestions",
        os.path.join(_V2_ROOT, "scripts", "review_improvement_suggestions.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "_has_forbidden_conflict"), "_has_forbidden_conflict 関数が必要"
    fn = mod._has_forbidden_conflict
    # 禁止ワードなし → conflict=False
    result, _ = fn({"suggested_change": "深夜帯の投稿頻度を増やす"}, "night_scout")
    assert result is False, "禁止ワードなしは conflict=False であるべき"


def t_review_script_forbidden_conflict_detected():
    spec = importlib.util.spec_from_file_location(
        "review_improvement_suggestions",
        os.path.join(_V2_ROOT, "scripts", "review_improvement_suggestions.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = mod._has_forbidden_conflict
    # 禁止ワードあり → conflict=True
    result, detail = fn({"suggested_change": "代理店パートナーを増やす"}, "night_scout")
    assert result is True, "禁止ワード '代理店' は conflict=True であるべき"
    assert detail, "detail が空"


def t_review_script_valid_risk_levels():
    spec = importlib.util.spec_from_file_location(
        "review_improvement_suggestions",
        os.path.join(_V2_ROOT, "scripts", "review_improvement_suggestions.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "VALID_RISK_LEVELS"), "VALID_RISK_LEVELS が必要"
    assert {"high", "medium", "low"} <= mod.VALID_RISK_LEVELS


_test("review_improvement_suggestions.py 存在", t_review_script_exists)
_test("VALID_STATUSES に5種類（WAITING_REVIEW/APPROVED/REJECTED/IMPORTED/CONVERTED_TO_RULE）", t_review_script_has_valid_statuses)
_test("_has_forbidden_conflict 関数あり・禁止ワードなし=False", t_review_script_has_forbidden_conflict_fn)
_test("_has_forbidden_conflict: 代理店ワード検出=True", t_review_script_forbidden_conflict_detected)
_test("VALID_RISK_LEVELS に high/medium/low が含まれる", t_review_script_valid_risk_levels)


# ============================================================
# Phase 4.2: check_learning_integrity
# ============================================================

print("\n=== Phase 4.2: check_learning_integrity ===")


def t_check_learning_integrity_exists():
    path = os.path.join(_V2_ROOT, "scripts", "check_learning_integrity.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_check_learning_integrity_valid_statuses():
    spec = importlib.util.spec_from_file_location(
        "check_learning_integrity",
        os.path.join(_V2_ROOT, "scripts", "check_learning_integrity.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    required = {"WAITING_REVIEW", "APPROVED", "REJECTED", "IMPORTED", "CONVERTED_TO_RULE"}
    missing = required - mod.VALID_SUGGESTION_STATUSES
    assert not missing, f"VALID_SUGGESTION_STATUSES に不足: {missing}"


_test("check_learning_integrity.py 存在", t_check_learning_integrity_exists)
_test("VALID_SUGGESTION_STATUSES に5種類含む", t_check_learning_integrity_valid_statuses)


# ============================================================
# Phase 4.3: export_learning_context
# ============================================================

print("\n=== Phase 4.3: export_learning_context ===")


def t_export_script_exists():
    path = os.path.join(_V2_ROOT, "scripts", "export_learning_context.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_export_script_has_export_all_files():
    spec = importlib.util.spec_from_file_location(
        "export_learning_context",
        os.path.join(_V2_ROOT, "scripts", "export_learning_context.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "export_all_files"), "export_all_files 関数が必要"


def t_export_script_backward_compat():
    spec = importlib.util.spec_from_file_location(
        "export_learning_context",
        os.path.join(_V2_ROOT, "scripts", "export_learning_context.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "export_learning_context"), "後方互換: export_learning_context 関数が必要"


def t_export_redact_secrets():
    spec = importlib.util.spec_from_file_location(
        "export_learning_context",
        os.path.join(_V2_ROOT, "scripts", "export_learning_context.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = mod._redact_secrets
    row = {"sa_json": "secret-value", "name": "テスト", "api_key": "key123"}
    result = fn(row)
    assert result["sa_json"] != "secret-value", f"sa_json がマスクされていない: {result['sa_json']}"
    assert result["api_key"] != "key123", f"api_key がマスクされていない: {result['api_key']}"
    assert result["name"] == "テスト", "name は変更不要"


_test("export_learning_context.py 存在", t_export_script_exists)
_test("export_all_files 関数あり", t_export_script_has_export_all_files)
_test("後方互換: export_learning_context 関数あり", t_export_script_backward_compat)
_test("_redact_secrets: sa_json/api_key をマスク", t_export_redact_secrets)


# ============================================================
# Phase 4.3: import_improvement_suggestions
# ============================================================

print("\n=== Phase 4.3: import_improvement_suggestions ===")


def t_import_script_exists():
    path = os.path.join(_V2_ROOT, "scripts", "import_improvement_suggestions.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_import_script_has_hermes_dir():
    spec = importlib.util.spec_from_file_location(
        "import_improvement_suggestions",
        os.path.join(_V2_ROOT, "scripts", "import_improvement_suggestions.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "HERMES_IMPORT_DIR"), "HERMES_IMPORT_DIR が必要"
    assert "hermes" in mod.HERMES_IMPORT_DIR.lower(), "HERMES_IMPORT_DIR に 'hermes' が含まれること"


def t_import_script_forbidden_conflict_fn():
    spec = importlib.util.spec_from_file_location(
        "import_improvement_suggestions",
        os.path.join(_V2_ROOT, "scripts", "import_improvement_suggestions.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "_check_forbidden_conflict"), "_check_forbidden_conflict が必要"
    # 禁止ワード「代理店」含む提案を検出（suggested_change フィールドで確認）
    raw = {
        "suggested_change": "代理店パートナー募集を増やす",
        "current_behavior": "",
        "reason": "",
    }
    conflict, detail = mod._check_forbidden_conflict(raw, "night_scout")
    assert conflict is True, "代理店パターンは conflict=True であるべき"


def t_import_script_waiting_review_default():
    """インポートされた提案のデフォルトステータスが WAITING_REVIEW であること。"""
    spec = importlib.util.spec_from_file_location(
        "import_improvement_suggestions",
        os.path.join(_V2_ROOT, "scripts", "import_improvement_suggestions.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # import 関数内で WAITING_REVIEW が使われていること
    import inspect
    src = inspect.getsource(mod)
    assert "WAITING_REVIEW" in src, "インポート時に WAITING_REVIEW をデフォルトにすること"


_test("import_improvement_suggestions.py 存在", t_import_script_exists)
_test("HERMES_IMPORT_DIR 定数あり・hermes パス含む", t_import_script_has_hermes_dir)
_test("_check_forbidden_conflict: 代理店ワード検出", t_import_script_forbidden_conflict_fn)
_test("WAITING_REVIEW がデフォルトステータス", t_import_script_waiting_review_default)


# ============================================================
# Phase 4.4: weekly_report_builder + generate_weekly_growth_report
# ============================================================

print("\n=== Phase 4.4: weekly_report_builder ===")


def t_weekly_report_builder_exists():
    path = os.path.join(_V2_ROOT, "src", "learning", "weekly_report_builder.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_weekly_report_builder_build_fn():
    from learning.weekly_report_builder import build_weekly_report
    now = datetime(2026, 6, 7, 0, 0, 0, tzinfo=timezone.utc)
    result = build_weekly_report(
        "night_scout",
        posted_results=[
            {"post_id": "p1", "platform": "x", "generation_type": "video_clip_reference",
             "posted_at": "2026-06-05T12:00:00+00:00",
             "views": 800, "likes": 30, "comments": 5, "follows": 2, "engagement_rate": 0.045}
        ],
        queue_items=[
            {"status": "READY", "generation_mode": "video_clip_reference"}
        ],
        learning_rules=[{"active": True}],
        suggestions=[{"status": "WAITING_REVIEW"}],
        category_scores={},
        now=now,
    )
    assert isinstance(result, dict), f"dict を期待: {type(result)}"
    assert result["account_id"] == "night_scout"
    assert "period" in result
    assert result["meta"]["auto_apply"] is False


def t_weekly_report_builder_markdown_fn():
    from learning.weekly_report_builder import build_weekly_report, build_markdown_report
    now = datetime(2026, 6, 7, 0, 0, 0, tzinfo=timezone.utc)
    report = build_weekly_report(
        "liver_manager",
        posted_results=[],
        queue_items=[],
        learning_rules=[],
        suggestions=[],
        category_scores={},
        now=now,
    )
    md = build_markdown_report(report)
    assert isinstance(md, str), f"str を期待: {type(md)}"
    assert "liver_manager" in md


def t_weekly_report_no_auto_apply():
    from learning.weekly_report_builder import build_weekly_report
    now = datetime(2026, 6, 7, tzinfo=timezone.utc)
    report = build_weekly_report(
        "night_scout",
        posted_results=[],
        queue_items=[],
        learning_rules=[],
        suggestions=[],
        category_scores={},
        now=now,
    )
    assert report["meta"]["auto_apply"] is False, "auto_apply=False であること（自動反映禁止）"


def t_generate_weekly_report_script_exists():
    path = os.path.join(_V2_ROOT, "scripts", "generate_weekly_growth_report.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_generate_weekly_report_supported_accounts():
    spec = importlib.util.spec_from_file_location(
        "generate_weekly_growth_report",
        os.path.join(_V2_ROOT, "scripts", "generate_weekly_growth_report.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "SUPPORTED_ACCOUNTS"), "SUPPORTED_ACCOUNTS が必要"
    assert "night_scout" in mod.SUPPORTED_ACCOUNTS
    assert "liver_manager" in mod.SUPPORTED_ACCOUNTS


_test("weekly_report_builder.py 存在", t_weekly_report_builder_exists)
_test("build_weekly_report: dict返却・auto_apply=False", t_weekly_report_builder_build_fn)
_test("build_markdown_report: str返却", t_weekly_report_builder_markdown_fn)
_test("週次レポート auto_apply=False 必須", t_weekly_report_no_auto_apply)
_test("generate_weekly_growth_report.py 存在", t_generate_weekly_report_script_exists)
_test("SUPPORTED_ACCOUNTS に night_scout/liver_manager", t_generate_weekly_report_supported_accounts)


# ============================================================
# Phase 4.5: activate_learning_rule
# ============================================================

print("\n=== Phase 4.5: activate_learning_rule ===")


def t_activate_script_exists():
    path = os.path.join(_V2_ROOT, "scripts", "activate_learning_rule.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_activate_has_prohibited_patterns():
    spec = importlib.util.spec_from_file_location(
        "activate_learning_rule",
        os.path.join(_V2_ROOT, "scripts", "activate_learning_rule.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "PROHIBITED_RULE_PATTERNS"), "PROHIBITED_RULE_PATTERNS が必要"
    patterns = mod.PROHIBITED_RULE_PATTERNS
    assert "night_scout" in patterns, "night_scout 固有禁止パターンが必要"
    assert "liver_manager" in patterns, "liver_manager 固有禁止パターンが必要"
    assert "代理店" in patterns["night_scout"], "night_scout: 代理店 が禁止パターンに必要"
    assert "情報商材" in patterns["liver_manager"], "liver_manager: 情報商材 が禁止パターンに必要"


def t_activate_forbidden_blocked():
    """_check_forbidden: 禁止パターンはブロックされる。"""
    spec = importlib.util.spec_from_file_location(
        "activate_learning_rule",
        os.path.join(_V2_ROOT, "scripts", "activate_learning_rule.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = mod._check_forbidden
    blocked, matched = fn("代理店パートナーを増やす戦略", "night_scout")
    assert blocked is True, "代理店パターンはブロックされるべき"
    assert matched, "matched が空"


def t_activate_clean_not_blocked():
    """_check_forbidden: クリーンなテキストはブロックされない。"""
    spec = importlib.util.spec_from_file_location(
        "activate_learning_rule",
        os.path.join(_V2_ROOT, "scripts", "activate_learning_rule.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = mod._check_forbidden
    blocked, matched = fn("深夜帯の投稿頻度を増やす", "night_scout")
    assert blocked is False, "クリーンなテキストはブロックしない"


def t_activate_create_rule_active_false():
    """create_rule_from_suggestion: dry-run で True を返し、active=false が設計に含まれること。"""
    spec = importlib.util.spec_from_file_location(
        "activate_learning_rule",
        os.path.join(_V2_ROOT, "scripts", "activate_learning_rule.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from sheets_client import MockSheetsClient
    import inspect
    sheets = MockSheetsClient()
    # MockSheetsClient に仮の提案データを注入（_find_suggestion が参照するフィールド名）
    sheets._prompt_improvement_suggestions = [
        {
            "suggestion_id": "sug-test-001",
            "account_id": "night_scout",
            "suggestion_type": "rule_addition",
            "suggested_change": "深夜帯の投稿頻度を増やす",
            "status": "APPROVED",
            "risk_level": "low",
        }
    ]
    # dry-run=True → True を返すことを確認
    result = mod.create_rule_from_suggestion(sheets, "sug-test-001", dry_run=True)
    assert result is True, f"dry_run=True では True を返すべき: {result}"
    # ソースコードに "active": "false" が含まれることを確認（設計保証）
    src = inspect.getsource(mod.create_rule_from_suggestion)
    assert '"active": "false"' in src, 'create_rule_from_suggestion が "active": "false" でルールを作成すること'


def t_activate_confirm_required():
    """activate_rule: dry_run=True（デフォルト）では実際の activate が起きないこと。

    CLIレベルでは --confirm-activate フラグなしは dry_run=True で呼ばれる。
    この関数では dry_run=True 時の安全動作を確認する。
    """
    spec = importlib.util.spec_from_file_location(
        "activate_learning_rule",
        os.path.join(_V2_ROOT, "scripts", "activate_learning_rule.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from sheets_client import MockSheetsClient
    sheets = MockSheetsClient()
    # _find_rule が参照するフィールド名
    sheets._learning_rules = [
        {
            "rule_id": "rule-test-001",
            "account_id": "night_scout",
            "description": "深夜帯の投稿頻度を増やす",
            "condition": "",
            "action": "",
            "active": "false",
        }
    ]
    # dry_run=True（--confirm-activate なしに相当）→ True が返るが実際には書き込みしない
    result = mod.activate_rule(sheets, "rule-test-001", dry_run=True)
    # dry_run=True では True（確認OK）を返すが、データは書き換えない
    assert result is True, "dry_run=True でも True を返す（確認完了）"
    # 元データの active は変更されていないこと
    rule = sheets._learning_rules[0]
    assert str(rule.get("active", "false")).lower() == "false", \
        "dry_run=True では active=false のまま変更しない"


_test("activate_learning_rule.py 存在", t_activate_script_exists)
_test("PROHIBITED_RULE_PATTERNS あり・night_scout/liver_manager 固有パターン", t_activate_has_prohibited_patterns)
_test("_check_forbidden: 代理店パターンはブロック", t_activate_forbidden_blocked)
_test("_check_forbidden: クリーンテキストはブロックしない", t_activate_clean_not_blocked)
_test("create_rule_from_suggestion: dry-run で active=False", t_activate_create_rule_active_false)
_test("activate_rule: --confirm-activate なしで active=True 不可", t_activate_confirm_required)


# ============================================================
# fixtures 確認
# ============================================================

print("\n=== fixtures: Phase 4.2〜4.5 ===")


def t_fixture_weekly_growth_report():
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_weekly_growth_report.json")
    assert os.path.isfile(path), f"見つかりません: {path}"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["meta"]["auto_apply"] is False


def t_fixture_hermes_export_context():
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_hermes_export_context.json")
    assert os.path.isfile(path), f"見つかりません: {path}"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["files_exported"]) == 4, "4ファイルが出力されること"


def t_fixture_hermes_import_suggestions():
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_hermes_import_suggestions.json")
    assert os.path.isfile(path), f"見つかりません: {path}"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    statuses = {s["status"] for s in data["suggestions"]}
    assert statuses == {"WAITING_REVIEW"}, f"全提案が WAITING_REVIEW であるべき: {statuses}"


def t_fixture_learning_rule_activation():
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_learning_rule_activation.json")
    assert os.path.isfile(path), f"見つかりません: {path}"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["meta"]["active_auto_set"] is False


_test("sample_weekly_growth_report.json: auto_apply=False", t_fixture_weekly_growth_report)
_test("sample_hermes_export_context.json: 4ファイル出力", t_fixture_hermes_export_context)
_test("sample_hermes_import_suggestions.json: 全提案 WAITING_REVIEW", t_fixture_hermes_import_suggestions)
_test("sample_learning_rule_activation.json: active_auto_set=False", t_fixture_learning_rule_activation)


# ============================================================
# 結果表示
# ============================================================

print("\n" + "=" * 60)
print(f"  test_phase42_45_learning_workflow.py 結果: PASS={_PASS} FAIL={_FAIL}")
print("=" * 60)

for name, ok, msg in _tests:
    icon = "[PASS]" if ok else "[FAIL]"
    print(f"  {icon} {name}")
    if not ok and msg:
        print(f"         → {msg}")

if _FAIL > 0:
    sys.exit(1)
sys.exit(0)
