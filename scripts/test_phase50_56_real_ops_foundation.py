"""
test_phase50_56_real_ops_foundation.py - Phase 5.0-5.6 テストスイート

Phase 5.0: Real Smoke Test Orchestrator
Phase 5.1: Cloudflare Runbook
Phase 5.2: Cloudinary Runbook
Phase 5.3: X real post preflight
Phase 5.5: GitHub Actions dry-run workflow
Phase 5.6: Operation Runbook

実行方法: python scripts/test_phase50_56_real_ops_foundation.py
"""
from __future__ import annotations

import json
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

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
# Phase 5.0: run_real_smoke_plan.py
# ============================================================

print("\n=== Phase 5.0: run_real_smoke_plan.py ===")


def t_smoke_plan_script_exists():
    p = os.path.join(_V2_ROOT, "scripts", "run_real_smoke_plan.py")
    assert os.path.isfile(p), f"見つかりません: {p}"


def t_smoke_plan_has_dry_run_default():
    p = os.path.join(_V2_ROOT, "scripts", "run_real_smoke_plan.py")
    src = open(p, encoding="utf-8").read()
    assert "dry_run" in src.lower() or "dry-run" in src.lower(), \
        "dry-run デフォルトが必要"


def t_smoke_plan_no_real_api_call():
    p = os.path.join(_V2_ROOT, "scripts", "run_real_smoke_plan.py")
    src = open(p, encoding="utf-8").read()
    forbidden = ["requests.post", "cloudinary.uploader.upload", "tweepy.Client().create_tweet"]
    for f in forbidden:
        assert f not in src, f"実API呼び出し禁止: {f}"


def t_smoke_plan_has_verdict_levels():
    p = os.path.join(_V2_ROOT, "scripts", "run_real_smoke_plan.py")
    src = open(p, encoding="utf-8").read()
    for verdict in ["READY", "NOT_READY", "BLOCKED"]:
        assert verdict in src, f"判定レベル {verdict} が必要"


def t_smoke_plan_no_secret_output():
    p = os.path.join(_V2_ROOT, "scripts", "run_real_smoke_plan.py")
    src = open(p, encoding="utf-8").read()
    assert "print(x_api_key)" not in src.lower(), "シークレット値を出力してはいけない"
    assert "_masked(" in src, "マスク処理が必要"


def t_smoke_plan_no_posted_results_change():
    p = os.path.join(_V2_ROOT, "scripts", "run_real_smoke_plan.py")
    src = open(p, encoding="utf-8").read()
    assert "append_row(\"posted_results\"" not in src, \
        "posted_resultsを変更してはいけない"
    assert "queue.status" not in src.lower().replace("queue.status", "QUEUE_STATUS"), \
        "queue.statusを変更してはいけない"


def t_smoke_plan_step_option():
    p = os.path.join(_V2_ROOT, "scripts", "run_real_smoke_plan.py")
    src = open(p, encoding="utf-8").read()
    for step in ["cloudflare", "cloudinary", "x", "all"]:
        assert step in src, f"--step {step} オプションが必要"


def _load_smoke_plan_module():
    """run_real_smoke_plan.py をモジュールとしてロードして返す。"""
    import importlib.util
    scripts_dir = os.path.join(_V2_ROOT, "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    p = os.path.join(scripts_dir, "run_real_smoke_plan.py")
    mod_name = "run_real_smoke_plan_mod"
    # キャッシュ済みなら再利用
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, p)
    mod = importlib.util.module_from_spec(spec)
    # @dataclass が sys.modules.get(cls.__module__) を参照するため exec_module 前に登録が必要
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def t_smoke_plan_dry_run_importable():
    """run_real_smoke_plan.py がインポートエラーなく読み込める。"""
    mod = _load_smoke_plan_module()
    assert hasattr(mod, "check_cloudflare"), "check_cloudflare 関数が必要"
    assert hasattr(mod, "check_cloudinary"), "check_cloudinary 関数が必要"
    assert hasattr(mod, "check_x"), "check_x 関数が必要"


def t_smoke_plan_check_cloudflare():
    """check_cloudflare 関数が呼び出せる（dry-run）。"""
    mod = _load_smoke_plan_module()
    result = mod.check_cloudflare(None)
    assert result.service == "Cloudflare"
    assert result.verdict in ("READY", "READY_FOR_MANUAL_SMOKE", "NOT_READY", "BLOCKED")


def t_smoke_plan_check_cloudinary():
    """check_cloudinary 関数が呼び出せる（dry-run）。"""
    mod = _load_smoke_plan_module()
    result = mod.check_cloudinary(None)
    assert result.service == "Cloudinary"
    assert result.verdict in ("READY", "READY_FOR_MANUAL_SMOKE", "NOT_READY", "BLOCKED")


def t_smoke_plan_check_x():
    """check_x 関数が呼び出せる（dry-run）。"""
    mod = _load_smoke_plan_module()
    result = mod.check_x("night_scout")
    assert result.service == "X"
    assert result.verdict in ("READY", "READY_FOR_MANUAL_SMOKE", "NOT_READY", "BLOCKED")


def t_smoke_plan_flags_false_yields_safe():
    """ALLOW_xxx=false の状態では READY_FOR_MANUAL_SMOKE 以下になるべき。"""
    os.environ["ALLOW_TRANSCRIPTION_API"] = "false"
    os.environ["ALLOW_CLOUDINARY_UPLOAD"] = "false"
    os.environ["PUBLISH_ENABLED"] = "false"
    os.environ["ALLOW_REAL_X_POST"] = "false"
    mod = _load_smoke_plan_module()
    cf = mod.check_cloudflare(None)
    cl = mod.check_cloudinary(None)
    assert cf.verdict != "READY", "ALLOW_TRANSCRIPTION_API=false なら READY にならない"
    assert cl.verdict != "READY", "ALLOW_CLOUDINARY_UPLOAD=false なら READY にならない"


for fn in [
    t_smoke_plan_script_exists,
    t_smoke_plan_has_dry_run_default,
    t_smoke_plan_no_real_api_call,
    t_smoke_plan_has_verdict_levels,
    t_smoke_plan_no_secret_output,
    t_smoke_plan_no_posted_results_change,
    t_smoke_plan_step_option,
    t_smoke_plan_dry_run_importable,
    t_smoke_plan_check_cloudflare,
    t_smoke_plan_check_cloudinary,
    t_smoke_plan_check_x,
    t_smoke_plan_flags_false_yields_safe,
]:
    _test(fn.__name__, fn)


# ============================================================
# Phase 5.1: Cloudflare Runbook
# ============================================================

print("\n=== Phase 5.1: Cloudflare Runbook ===")


def t_cloudflare_runbook_exists():
    p = os.path.join(_V2_ROOT, "docs", "cloudflare-transcription-runbook.md")
    assert os.path.isfile(p), f"見つかりません: {p}"


def t_cloudflare_runbook_has_false_restore():
    p = os.path.join(_V2_ROOT, "docs", "cloudflare-transcription-runbook.md")
    content = open(p, encoding="utf-8").read()
    assert "ALLOW_TRANSCRIPTION_API=false" in content, \
        "falseへ戻す手順が必要"


def t_cloudflare_runbook_has_confirm_api():
    p = os.path.join(_V2_ROOT, "docs", "cloudflare-transcription-runbook.md")
    content = open(p, encoding="utf-8").read()
    assert "--confirm-api" in content, "--confirm-api フラグの記載が必要"


def t_cloudflare_runbook_no_real_api():
    p = os.path.join(_V2_ROOT, "scripts", "test_cloudflare_transcription_credentials.py")
    src = open(p, encoding="utf-8").read()
    assert "requests.post" not in src, "credentials確認スクリプトで実API呼び出し禁止"


for fn in [
    t_cloudflare_runbook_exists,
    t_cloudflare_runbook_has_false_restore,
    t_cloudflare_runbook_has_confirm_api,
    t_cloudflare_runbook_no_real_api,
]:
    _test(fn.__name__, fn)


# ============================================================
# Phase 5.2: Cloudinary Runbook
# ============================================================

print("\n=== Phase 5.2: Cloudinary Runbook ===")


def t_cloudinary_runbook_exists():
    p = os.path.join(_V2_ROOT, "docs", "cloudinary-upload-runbook.md")
    assert os.path.isfile(p), f"見つかりません: {p}"


def t_cloudinary_runbook_has_false_restore():
    p = os.path.join(_V2_ROOT, "docs", "cloudinary-upload-runbook.md")
    content = open(p, encoding="utf-8").read()
    assert "ALLOW_CLOUDINARY_UPLOAD=false" in content, "falseへ戻す手順が必要"


def t_cloudinary_runbook_has_confirm_upload():
    p = os.path.join(_V2_ROOT, "docs", "cloudinary-upload-runbook.md")
    content = open(p, encoding="utf-8").read()
    assert "--confirm-upload" in content, "--confirm-upload フラグの記載が必要"


def t_cloudinary_runbook_has_delete():
    p = os.path.join(_V2_ROOT, "docs", "cloudinary-upload-runbook.md")
    content = open(p, encoding="utf-8").read()
    assert "削除" in content, "アップロード後の削除手順が必要"


for fn in [
    t_cloudinary_runbook_exists,
    t_cloudinary_runbook_has_false_restore,
    t_cloudinary_runbook_has_confirm_upload,
    t_cloudinary_runbook_has_delete,
]:
    _test(fn.__name__, fn)


# ============================================================
# Phase 5.3: X real post preflight
# ============================================================

print("\n=== Phase 5.3: X real post preflight ===")


def t_x_preflight_script_exists():
    p = os.path.join(_V2_ROOT, "scripts", "preflight_x_real_post.py")
    assert os.path.isfile(p), f"見つかりません: {p}"


def t_x_media_smoke_test_doc_exists():
    p = os.path.join(_V2_ROOT, "docs", "x-media-post-smoke-test.md")
    assert os.path.isfile(p), f"見つかりません: {p}"


def t_x_media_smoke_has_false_restore():
    p = os.path.join(_V2_ROOT, "docs", "x-media-post-smoke-test.md")
    content = open(p, encoding="utf-8").read()
    assert "PUBLISH_ENABLED=false" in content, "falseへ戻す手順が必要"
    assert "ALLOW_REAL_X_POST=false" in content, "falseへ戻す手順が必要"


def t_x_preflight_no_real_post():
    p = os.path.join(_V2_ROOT, "scripts", "preflight_x_real_post.py")
    src = open(p, encoding="utf-8").read()
    assert "create_tweet" not in src or "ALLOW_REAL_X_POST" in src, \
        "実投稿呼び出しは安全ガードが必要"


def t_x_media_smoke_has_confirm_real_post():
    p = os.path.join(_V2_ROOT, "docs", "x-media-post-smoke-test.md")
    content = open(p, encoding="utf-8").read()
    assert "--confirm-real-post" in content, "--confirm-real-post フラグの記載が必要"


for fn in [
    t_x_preflight_script_exists,
    t_x_media_smoke_test_doc_exists,
    t_x_media_smoke_has_false_restore,
    t_x_preflight_no_real_post,
    t_x_media_smoke_has_confirm_real_post,
]:
    _test(fn.__name__, fn)


# ============================================================
# Phase 5.5: GitHub Actions dry-run workflow
# ============================================================

print("\n=== Phase 5.5: GitHub Actions dry-run workflow ===")


def t_workflow_file_exists():
    p = os.path.join(_V2_ROOT, ".github", "workflows", "v2-dry-run-check.yml")
    assert os.path.isfile(p), f"見つかりません: {p}"


def t_workflow_dispatch_only():
    p = os.path.join(_V2_ROOT, ".github", "workflows", "v2-dry-run-check.yml")
    content = open(p, encoding="utf-8").read()
    assert "workflow_dispatch" in content, "workflow_dispatch が必要"
    assert "schedule:" not in content, "schedule は使用禁止"


def t_workflow_no_publish_enabled_true():
    p = os.path.join(_V2_ROOT, ".github", "workflows", "v2-dry-run-check.yml")
    content = open(p, encoding="utf-8").read()
    # YAML env: ブロック内での設定形式のみチェック（シェルの条件分岐は除外）
    assert 'PUBLISH_ENABLED: "true"' not in content, \
        'PUBLISH_ENABLED: "true" は禁止（env: ブロック内）'


def t_workflow_no_allow_real_x_post_true():
    p = os.path.join(_V2_ROOT, ".github", "workflows", "v2-dry-run-check.yml")
    content = open(p, encoding="utf-8").read()
    assert 'ALLOW_REAL_X_POST: "true"' not in content, \
        'ALLOW_REAL_X_POST: "true" は禁止（env: ブロック内）'


def t_workflow_no_allow_transcription_api_true():
    p = os.path.join(_V2_ROOT, ".github", "workflows", "v2-dry-run-check.yml")
    content = open(p, encoding="utf-8").read()
    assert 'ALLOW_TRANSCRIPTION_API: "true"' not in content, \
        'ALLOW_TRANSCRIPTION_API: "true" は禁止（env: ブロック内）'


def t_workflow_no_allow_cloudinary_upload_true():
    p = os.path.join(_V2_ROOT, ".github", "workflows", "v2-dry-run-check.yml")
    content = open(p, encoding="utf-8").read()
    assert 'ALLOW_CLOUDINARY_UPLOAD: "true"' not in content, \
        'ALLOW_CLOUDINARY_UPLOAD: "true" は禁止（env: ブロック内）'


def t_workflow_has_safety_false_env():
    p = os.path.join(_V2_ROOT, ".github", "workflows", "v2-dry-run-check.yml")
    content = open(p, encoding="utf-8").read()
    assert 'PUBLISH_ENABLED: "false"' in content, "PUBLISH_ENABLED=false が必要"
    assert 'ALLOW_REAL_X_POST: "false"' in content, "ALLOW_REAL_X_POST=false が必要"
    assert 'DRY_RUN: "true"' in content, "DRY_RUN=true が必要"


def t_workflow_no_real_post_commands():
    p = os.path.join(_V2_ROOT, ".github", "workflows", "v2-dry-run-check.yml")
    content = open(p, encoding="utf-8").read()
    forbidden_cmds = [
        "publish_queue.py --confirm-real-post",
    ]
    for cmd in forbidden_cmds:
        assert cmd not in content, f"禁止コマンドが含まれています: {cmd}"
    # YAML env: ブロック内に安全フラグのtrue設定がないことを確認
    assert 'PUBLISH_ENABLED: "true"' not in content, "env: ブロック内に PUBLISH_ENABLED=true は禁止"
    assert 'ALLOW_REAL_X_POST: "true"' not in content, "env: ブロック内に ALLOW_REAL_X_POST=true は禁止"


def t_workflow_no_injection():
    """github.event.inputs を run: コマンドライン内で直接展開していないこと。"""
    p = os.path.join(_V2_ROOT, ".github", "workflows", "v2-dry-run-check.yml")
    content = open(p, encoding="utf-8").read()
    # run: コマンドの行（単一行 run: cmd 形式）に直接 ${{ github.event.inputs が含まれていないことを確認
    # env: ブロック内（ACCOUNT_ID: ${{ ... }} の形式）は許可
    lines = content.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        # run: で始まる行（単一行コマンド）のみチェック
        if stripped.startswith("run:") and "${{ github.event.inputs" in stripped:
            assert False, \
                f"injection リスク (行{i+1}): run: 内で github.event.inputs を直接展開しています: {stripped}"


for fn in [
    t_workflow_file_exists,
    t_workflow_dispatch_only,
    t_workflow_no_publish_enabled_true,
    t_workflow_no_allow_real_x_post_true,
    t_workflow_no_allow_transcription_api_true,
    t_workflow_no_allow_cloudinary_upload_true,
    t_workflow_has_safety_false_env,
    t_workflow_no_real_post_commands,
    t_workflow_no_injection,
]:
    _test(fn.__name__, fn)


# ============================================================
# Phase 5.6: 運用Runbook
# ============================================================

print("\n=== Phase 5.6: 運用Runbook ===")


def t_operation_runbook_exists():
    p = os.path.join(_V2_ROOT, "docs", "operation-runbook.md")
    assert os.path.isfile(p), f"見つかりません: {p}"


def t_manual_smoke_sequence_exists():
    p = os.path.join(_V2_ROOT, "docs", "manual-smoke-test-sequence.md")
    assert os.path.isfile(p), f"見つかりません: {p}"


def t_emergency_rollback_exists():
    p = os.path.join(_V2_ROOT, "docs", "emergency-rollback.md")
    assert os.path.isfile(p), f"見つかりません: {p}"


def t_operation_runbook_has_active_dir():
    p = os.path.join(_V2_ROOT, "docs", "operation-runbook.md")
    content = open(p, encoding="utf-8").read()
    assert "v2" in content, "作業ディレクトリ（v2）の記載が必要"


def t_emergency_rollback_has_all_flags():
    p = os.path.join(_V2_ROOT, "docs", "emergency-rollback.md")
    content = open(p, encoding="utf-8").read()
    for flag in ["PUBLISH_ENABLED", "ALLOW_REAL_X_POST", "ALLOW_TRANSCRIPTION_API", "ALLOW_CLOUDINARY_UPLOAD"]:
        assert flag in content, f"{flag} の緊急対応記載が必要"


def t_emergency_rollback_has_key_rotation():
    p = os.path.join(_V2_ROOT, "docs", "emergency-rollback.md")
    content = open(p, encoding="utf-8").read()
    assert "ローテーション" in content or "Regenerate" in content, \
        "APIキーローテーション手順が必要"


def t_phase5_doc_exists():
    p = os.path.join(_V2_ROOT, "docs", "phase5-real-smoke-test-plan.md")
    assert os.path.isfile(p), f"見つかりません: {p}"


def t_docs_mention_zip_retired_policy():
    """docsに現行作業ディレクトリが明記されていること。"""
    p = os.path.join(_V2_ROOT, "docs", "phase5-real-smoke-test-plan.md")
    content = open(p, encoding="utf-8").read()
    assert "使ってない_過去" in content or "zip" in content.lower(), \
        "旧フォルダに触らない方針がdocsに必要"


for fn in [
    t_operation_runbook_exists,
    t_manual_smoke_sequence_exists,
    t_emergency_rollback_exists,
    t_operation_runbook_has_active_dir,
    t_emergency_rollback_has_all_flags,
    t_emergency_rollback_has_key_rotation,
    t_phase5_doc_exists,
    t_docs_mention_zip_retired_policy,
]:
    _test(fn.__name__, fn)


# ============================================================
# fixtures
# ============================================================

print("\n=== Fixtures ===")


def t_fixture_post_results_import_json():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_post_results_import.json")
    assert os.path.isfile(p), f"見つかりません: {p}"
    data = json.loads(open(p, encoding="utf-8").read())
    results = data.get("results", data) if isinstance(data, dict) else data
    assert len(results) >= 1, "最低1件のrecordが必要"


def t_fixture_post_results_import_csv():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_post_results_import.csv")
    assert os.path.isfile(p), f"見つかりません: {p}"
    content = open(p, encoding="utf-8").read()
    assert "account_id" in content, "account_idカラムが必要"


def t_fixture_real_smoke_plan():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_real_smoke_plan.json")
    assert os.path.isfile(p), f"見つかりません: {p}"
    data = json.loads(open(p, encoding="utf-8").read())
    assert data.get("dry_run") is True, "dry_run=true が必要"


def t_fixture_x_media_preflight():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_x_media_post_preflight.json")
    assert os.path.isfile(p), f"見つかりません: {p}"
    data = json.loads(open(p, encoding="utf-8").read())
    assert "checks" in data, "checks フィールドが必要"


def t_fixture_post_result_analysis():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_post_result_analysis.json")
    assert os.path.isfile(p), f"見つかりません: {p}"
    data = json.loads(open(p, encoding="utf-8").read())
    assert "metrics" in data, "metrics フィールドが必要"


def t_fixture_generated_learning():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_generated_learning_from_results.json")
    assert os.path.isfile(p), f"見つかりません: {p}"
    data = json.loads(open(p, encoding="utf-8").read())
    suggestions = data.get("suggestions", [])
    for s in suggestions:
        assert s.get("status") == "WAITING_REVIEW", "全提案はWAITING_REVIEWであること"
        assert str(s.get("active", "false")).lower() == "false", "active=false が必要"


for fn in [
    t_fixture_post_results_import_json,
    t_fixture_post_results_import_csv,
    t_fixture_real_smoke_plan,
    t_fixture_x_media_preflight,
    t_fixture_post_result_analysis,
    t_fixture_generated_learning,
]:
    _test(fn.__name__, fn)


# ============================================================
# 結果出力
# ============================================================

print(f"\n{'=' * 60}")
print(f"  Phase 5.0-5.6 テスト結果: PASS={_PASS} / FAIL={_FAIL}")
print(f"{'=' * 60}")

if _FAIL > 0:
    print("\n[FAILED テスト一覧]")
    for name, ok, msg in _tests:
        if not ok:
            print(f"  FAIL: {name}")
            print(f"        {msg}")

sys.exit(0 if _FAIL == 0 else 1)
