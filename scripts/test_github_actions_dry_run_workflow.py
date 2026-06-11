"""
test_github_actions_dry_run_workflow.py - Phase 5.5 テストスイート

GitHub Actions dry-run workflow の内容を検証する。
実際に workflow を実行しない。ファイル内容のみ確認する。

実行方法: python scripts/test_github_actions_dry_run_workflow.py
"""
from __future__ import annotations

import os
import sys

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


WORKFLOW_PATH = os.path.join(_V2_ROOT, ".github", "workflows", "v2-dry-run-check.yml")


def _load_workflow() -> str:
    assert os.path.isfile(WORKFLOW_PATH), f"workflow ファイルが見つかりません: {WORKFLOW_PATH}"
    return open(WORKFLOW_PATH, encoding="utf-8").read()


# ============================================================
# 存在確認
# ============================================================

print("\n=== workflow ファイル存在確認 ===")


def t_workflow_file_exists():
    assert os.path.isfile(WORKFLOW_PATH), f"見つかりません: {WORKFLOW_PATH}"


_test("t_workflow_file_exists", t_workflow_file_exists)


# ============================================================
# トリガー確認
# ============================================================

print("\n=== トリガー確認 ===")


def t_has_workflow_dispatch():
    content = _load_workflow()
    assert "workflow_dispatch" in content, "workflow_dispatch が必要"


def t_no_schedule():
    content = _load_workflow()
    assert "schedule:" not in content, "schedule は使用禁止（dry-runのみ）"


def t_no_push_trigger():
    content = _load_workflow()
    # push/pull_request トリガーは使っても良いが、今回の設計では使わない
    # workflow_dispatch のみを確認
    assert "workflow_dispatch" in content, "workflow_dispatch が必要"


for fn in [t_has_workflow_dispatch, t_no_schedule, t_no_push_trigger]:
    _test(fn.__name__, fn)


# ============================================================
# 安全フラグ確認
# ============================================================

print("\n=== 安全フラグ確認（全てfalse固定）===")


def t_publish_enabled_false():
    content = _load_workflow()
    assert 'PUBLISH_ENABLED: "false"' in content, "PUBLISH_ENABLED=false が必要"


def t_allow_real_x_post_false():
    content = _load_workflow()
    assert 'ALLOW_REAL_X_POST: "false"' in content, "ALLOW_REAL_X_POST=false が必要"


def t_allow_real_threads_post_false():
    content = _load_workflow()
    assert 'ALLOW_REAL_THREADS_POST: "false"' in content, "ALLOW_REAL_THREADS_POST=false が必要"


def t_allow_transcription_api_false():
    content = _load_workflow()
    assert 'ALLOW_TRANSCRIPTION_API: "false"' in content, "ALLOW_TRANSCRIPTION_API=false が必要"


def t_allow_cloudinary_upload_false():
    content = _load_workflow()
    assert 'ALLOW_CLOUDINARY_UPLOAD: "false"' in content, "ALLOW_CLOUDINARY_UPLOAD=false が必要"


def t_dry_run_true():
    content = _load_workflow()
    assert 'DRY_RUN: "true"' in content, "DRY_RUN=true が必要"


for fn in [
    t_publish_enabled_false,
    t_allow_real_x_post_false,
    t_allow_real_threads_post_false,
    t_allow_transcription_api_false,
    t_allow_cloudinary_upload_false,
    t_dry_run_true,
]:
    _test(fn.__name__, fn)


# ============================================================
# 禁止パターン確認
# ============================================================

print("\n=== 禁止パターン確認 ===")


def t_no_publish_enabled_true():
    content = _load_workflow()
    assert 'PUBLISH_ENABLED: "true"' not in content, "PUBLISH_ENABLED=true は禁止"
    assert 'PUBLISH_ENABLED=true' not in content, "PUBLISH_ENABLED=true は禁止"


def t_no_allow_real_x_post_true():
    content = _load_workflow()
    assert 'ALLOW_REAL_X_POST: "true"' not in content, "ALLOW_REAL_X_POST=true は禁止"
    assert 'ALLOW_REAL_X_POST=true' not in content, "ALLOW_REAL_X_POST=true は禁止"


def t_no_allow_transcription_api_true():
    content = _load_workflow()
    assert 'ALLOW_TRANSCRIPTION_API: "true"' not in content, "ALLOW_TRANSCRIPTION_API=true は禁止"
    assert 'ALLOW_TRANSCRIPTION_API=true' not in content, "ALLOW_TRANSCRIPTION_API=true は禁止"


def t_no_allow_cloudinary_upload_true():
    content = _load_workflow()
    assert 'ALLOW_CLOUDINARY_UPLOAD: "true"' not in content, "ALLOW_CLOUDINARY_UPLOAD=true は禁止"
    assert 'ALLOW_CLOUDINARY_UPLOAD=true' not in content, "ALLOW_CLOUDINARY_UPLOAD=true は禁止"


def t_no_confirm_real_post():
    content = _load_workflow()
    assert "--confirm-real-post" not in content, \
        "workflow内で実投稿コマンドは禁止"


def t_no_real_post_publish_script():
    """publish_queue.py --confirm-real-post が workflow に含まれていないこと。"""
    content = _load_workflow()
    assert "publish_queue.py" not in content or "--confirm-real-post" not in content, \
        "実投稿コマンドは workflow に含めてはいけない"


for fn in [
    t_no_publish_enabled_true,
    t_no_allow_real_x_post_true,
    t_no_allow_transcription_api_true,
    t_no_allow_cloudinary_upload_true,
    t_no_confirm_real_post,
    t_no_real_post_publish_script,
]:
    _test(fn.__name__, fn)


# ============================================================
# セキュリティ確認（injection対策）
# ============================================================

print("\n=== セキュリティ確認（injection対策）===")


def t_no_injection_in_run():
    """run: 内で ${{ github.event.inputs.xxx }} を直接展開していないこと。"""
    content = _load_workflow()
    lines = content.split("\n")
    in_run_block = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        # run: ブロックの開始を検出
        if stripped.startswith("run:") or stripped == "run: |":
            in_run_block = True
            continue
        # インデントが減ったらブロック終了
        if in_run_block and stripped and not stripped.startswith("#"):
            # run: ブロック内のコマンド行
            if "${{ github.event.inputs" in line:
                assert False, \
                    f"injection リスク (行{i+1}): run: 内で github.event.inputs を直接展開: {line.strip()}"
            # 新しいYAMLキーが始まったらブロック終了
            if ":" in stripped and not stripped.startswith("-"):
                in_run_block = False


def t_no_github_head_ref_in_run():
    """github.head_ref を run: 内で直接使っていないこと。"""
    content = _load_workflow()
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if "${{ github.head_ref }}" in line and ("run:" in line or "python " in line):
            assert False, f"injection リスク (行{i+1}): github.head_ref を直接使用"


def t_no_secret_echo():
    """secrets 値を echo しないこと。"""
    content = _load_workflow()
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if "echo" in line and "secrets." in line:
            assert False, f"secrets値を echo してはいけない (行{i+1}): {line.strip()}"


for fn in [t_no_injection_in_run, t_no_github_head_ref_in_run, t_no_secret_echo]:
    _test(fn.__name__, fn)


# ============================================================
# 実行ステップ確認
# ============================================================

print("\n=== 実行ステップ確認 ===")


def t_has_safety_verification_step():
    content = _load_workflow()
    assert "Verify safety flags" in content or "安全フラグ" in content, \
        "安全フラグ確認ステップが必要"


def t_has_preflight_steps():
    content = _load_workflow()
    assert "preflight" in content.lower() or "Preflight" in content, \
        "preflight ステップが必要"


def t_has_integrity_check_steps():
    content = _load_workflow()
    assert "integrity" in content.lower(), "integrity check ステップが必要"


def t_has_phase5_test_step():
    content = _load_workflow()
    assert "test_phase50" in content or "phase50" in content or "Phase 5" in content, \
        "Phase 5 テストステップが必要"


def t_workflow_has_summary_step():
    content = _load_workflow()
    assert "Summary" in content or "summary" in content, "Summaryステップが必要"


for fn in [
    t_has_safety_verification_step,
    t_has_preflight_steps,
    t_has_integrity_check_steps,
    t_has_phase5_test_step,
    t_workflow_has_summary_step,
]:
    _test(fn.__name__, fn)


# ============================================================
# ドキュメント確認
# ============================================================

print("\n=== ドキュメント確認 ===")


def t_workflow_doc_exists():
    p = os.path.join(_V2_ROOT, "docs", "github-actions-dry-run-workflow.md")
    assert os.path.isfile(p), f"見つかりません: {p}"


def t_workflow_doc_has_workflow_dispatch():
    p = os.path.join(_V2_ROOT, "docs", "github-actions-dry-run-workflow.md")
    content = open(p, encoding="utf-8").read()
    assert "workflow_dispatch" in content, "workflow_dispatch の記載が必要"


def t_workflow_doc_no_schedule():
    p = os.path.join(_V2_ROOT, "docs", "github-actions-dry-run-workflow.md")
    content = open(p, encoding="utf-8").read()
    assert "schedule" in content.lower(), "scheduleに関する説明が必要"


def t_workflow_doc_has_security_note():
    p = os.path.join(_V2_ROOT, "docs", "github-actions-dry-run-workflow.md")
    content = open(p, encoding="utf-8").read()
    assert "injection" in content.lower() or "セキュリティ" in content, \
        "セキュリティ注意事項が必要"


for fn in [
    t_workflow_doc_exists,
    t_workflow_doc_has_workflow_dispatch,
    t_workflow_doc_no_schedule,
    t_workflow_doc_has_security_note,
]:
    _test(fn.__name__, fn)


# ============================================================
# 結果出力
# ============================================================

print(f"\n{'=' * 60}")
print(f"  Phase 5.5 テスト結果: PASS={_PASS} / FAIL={_FAIL}")
print(f"{'=' * 60}")

if _FAIL > 0:
    print("\n[FAILED テスト一覧]")
    for name, ok, msg in _tests:
        if not ok:
            print(f"  FAIL: {name}")
            print(f"        {msg}")

sys.exit(0 if _FAIL == 0 else 1)
