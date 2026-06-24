#!/usr/bin/env python3
"""test_content_workflows_safety.py — GitHub Actions workflow 安全性確認テスト

検証内容:
1. 全workflowに安全フラグ (PUBLISH_ENABLED=false 等) が設定されていること
2. content-pilot-publish.yml に beauty_account ガードが存在すること
3. workflow_dispatch inputs が env: 経由で使われていること（直接 ${{ }} を run: に渡していないこと）
4. schedule workflow が PUBLISH_ENABLED=false を維持していること
5. secrets が env: 経由で渡されていること（run: 内での直接展開なし）
"""
from __future__ import annotations

import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOWS_DIR = os.path.join(_ROOT, ".github", "workflows")

REQUIRED_SAFETY_FLAGS = [
    "PUBLISH_ENABLED",
    "ALLOW_REAL_X_POST",
    "ALLOW_REAL_THREADS_POST",
    "ALLOW_CLOUDINARY_UPLOAD",
]

EXPECTED_WORKFLOWS = [
    "content-daily-dry-run.yml",
    "content-pilot-publish.yml",
    "source-fetch-dry-run.yml",
    "threads-queue-worker.yml",
]


def _load(name: str) -> str:
    path = os.path.join(WORKFLOWS_DIR, name)
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_expected_workflows_exist():
    existing = os.listdir(WORKFLOWS_DIR)
    missing = [w for w in EXPECTED_WORKFLOWS if w not in existing]
    assert not missing, f"以下のworkflowが存在しません: {missing}"
    print(f"  [PASS] 必須workflow {len(EXPECTED_WORKFLOWS)}本 存在確認")


def test_safety_flags_in_all_new_workflows():
    failed = []
    for name in EXPECTED_WORKFLOWS:
        content = _load(name)
        for flag in REQUIRED_SAFETY_FLAGS:
            if flag not in content:
                failed.append(f"{name}: {flag} が未定義")
    assert not failed, "\n".join(failed)
    print(f"  [PASS] 全workflow に安全フラグ設定確認")


def test_publish_enabled_false_in_schedule_workflows():
    """schedule実行するworkflowは PUBLISH_ENABLED=false が必須。"""
    for name in ("content-daily-dry-run.yml", "source-fetch-dry-run.yml"):
        content = _load(name)
        assert 'PUBLISH_ENABLED: "false"' in content or "PUBLISH_ENABLED: 'false'" in content, \
            f"{name}: schedule workflow の PUBLISH_ENABLED が false でありません"
    print(f"  [PASS] schedule workflow の PUBLISH_ENABLED=false 確認")


def test_beauty_account_guard_in_pilot_publish():
    content = _load("content-pilot-publish.yml")
    assert "beauty_account" in content, "content-pilot-publish.yml に beauty_account ガードがありません"
    assert "exit 1" in content or "BLOCKED" in content, \
        "content-pilot-publish.yml に beauty_account ブロック処理がありません"
    print(f"  [PASS] content-pilot-publish.yml に beauty_account ガード確認")


def test_no_direct_expression_in_run_steps():
    """run: ブロック内のシェルスクリプト行に ${{ github.event.inputs.* }} を直接埋め込んでいないことを確認。
    env: / name: / if: フィールドは安全なので除外。$VAR 形式での利用は安全。"""
    unsafe_inputs = re.compile(r'\$\{\{[^}]*github\.event\.inputs\.[^}]+\}\}')
    # YAML キーとして安全なコンテキスト（値がシェル実行されない）
    safe_yaml_keys = re.compile(r'^\s*(name|env|if|id|uses|with|needs|outputs)\s*:')
    failed = []
    for wf_name in EXPECTED_WORKFLOWS:
        content = _load(wf_name)
        in_run_block = False
        run_indent = 0
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if stripped.startswith("#"):
                continue
            # run: ブロック開始検出
            if re.match(r'run:\s*\|', stripped):
                in_run_block = True
                run_indent = indent
                continue
            if re.match(r'run:\s*$', stripped):
                in_run_block = True
                run_indent = indent
                continue
            # run: ブロック外に戻ったか判定
            if in_run_block and stripped and indent <= run_indent and not stripped.startswith("|"):
                in_run_block = False
            # run: ブロック内のシェル行で unsafe expression チェック
            if in_run_block and unsafe_inputs.search(line):
                failed.append(f"{wf_name}:{i}: シェル実行行に ${{{{ inputs.* }}}} が直接使われています: {line.strip()!r}")
    assert not failed, "\n".join(failed)
    print(f"  [PASS] run: ブロック内の直接 expression 展開なし確認")


def test_secrets_via_env_not_run():
    """secrets.* を run: ブロック内に直接埋め込んでいないことを確認。"""
    # run: 内で ${{ secrets.* }} を使っているパターン（env: での参照は安全）
    unsafe_pattern = re.compile(
        r'run:.*\$\{\{\s*secrets\.',
        re.MULTILINE | re.DOTALL
    )
    failed = []
    for name in EXPECTED_WORKFLOWS:
        content = _load(name)
        # 行単位でチェック
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r'\$\{\{\s*secrets\.', stripped) and stripped.startswith("run:"):
                failed.append(f"{name}:{i}: run: 行に secrets が直接展開されています")
    assert not failed, "\n".join(failed)
    print(f"  [PASS] secrets の直接 run: 展開なし確認")


def test_pilot_publish_x_blocked_in_actions():
    """content-pilot-publish.yml で X 実投稿が GitHub Actions から自動実行されないこと。"""
    content = _load("content-pilot-publish.yml")
    assert "402" in content or "x-api-billing-blocker" in content or "X Developer Portal" in content, \
        "content-pilot-publish.yml に X 402 ブロッカー対応の説明がありません"
    assert 'ALLOW_REAL_X_POST: "true"' not in content and "ALLOW_REAL_X_POST: 'true'" not in content, \
        "content-pilot-publish.yml で ALLOW_REAL_X_POST=true が設定されています（禁止）"
    print(f"  [PASS] content-pilot-publish.yml の X 実投稿ブロック確認")


def test_pilot_publish_account_specific_secrets():
    """content-pilot-publish.yml にアカウント固有の Threads secrets が渡されていること。

    threads_credentials.py は THREADS_ACCESS_TOKEN_{ACCOUNT_ID_UPPER} を優先するため、
    workflow で渡さないと BLOCKED_MISSING_CREDENTIALS になる。
    """
    content = _load("content-pilot-publish.yml")
    required = [
        "THREADS_ACCESS_TOKEN_NIGHT_SCOUT",
        "THREADS_USER_ID_NIGHT_SCOUT",
        "THREADS_ACCESS_TOKEN_LIVER_MANAGER",
        "THREADS_USER_ID_LIVER_MANAGER",
    ]
    missing = [k for k in required if k not in content]
    assert not missing, f"content-pilot-publish.yml に account-specific secrets がありません: {missing}"
    # secrets.NAME 形式で参照されていることも確認
    for key in required:
        assert f"secrets.{key}" in content, \
            f"content-pilot-publish.yml: {key} が secrets.{key} から渡されていません"
    print(f"  [PASS] content-pilot-publish.yml に account-specific Threads secrets ({len(required)}件) 確認")


def test_threads_queue_worker_manual_only_and_safe():
    content = _load("threads-queue-worker.yml")
    assert "workflow_dispatch:" in content, "threads-queue-worker.yml に workflow_dispatch がありません"
    assert "schedule:" not in content, "threads-queue-worker.yml に schedule が入っています"
    assert "process_threads_queue.py" in content, "threads queue worker が process_threads_queue.py を呼んでいません"
    assert content.find("Queue worker dry-run") < content.find("Process queue"), \
        "実処理前の Queue worker dry-run が確認できません"
    assert "publish_x_post.py" not in content, "threads-queue-worker.yml が X publisher を呼んでいます"
    assert '"beauty_account"' not in content, "threads-queue-worker.yml に beauty_account option が入っています"
    assert "confirm_real_post" in content and "ALLOW_REAL_THREADS_POST" in content, \
        "real_post 安全確認が不足しています"
    assert "THREADS_ACCESS_TOKEN_NIGHT_SCOUT" in content and "GCP_SA_JSON_BASE64" in content, \
        "threads worker に必要な account-specific secrets / Sheets env が不足しています"
    assert "X_API_KEY" not in content and "X_ACCESS_TOKEN" not in content, \
        "threads worker に X secrets が含まれています"
    print("  [PASS] threads-queue-worker.yml manual-only / safe 確認")


def main():
    tests = [
        test_expected_workflows_exist,
        test_safety_flags_in_all_new_workflows,
        test_publish_enabled_false_in_schedule_workflows,
        test_beauty_account_guard_in_pilot_publish,
        test_no_direct_expression_in_run_steps,
        test_secrets_via_env_not_run,
        test_pilot_publish_x_blocked_in_actions,
        test_pilot_publish_account_specific_secrets,
        test_threads_queue_worker_manual_only_and_safe,
    ]
    passed = 0
    failed = 0
    print("\n=== test_content_workflows_safety ===")
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR] {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n結果: PASS={passed} FAIL={failed} / {len(tests)}件")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
