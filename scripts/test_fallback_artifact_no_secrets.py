#!/usr/bin/env python3
"""test_fallback_artifact_no_secrets.py — fallback JSON に secret が含まれないことと、
workflow に artifact upload が追加されていることを確認する。"""
from __future__ import annotations
import sys, json, tempfile, os
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

PASS_COUNT = FAIL_COUNT = 0


def check(label: str, cond: bool) -> None:
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        print(f"  PASS {label}")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL {label}")


print("=== test_fallback_artifact_no_secrets ===\n")

import scripts.process_threads_queue as ptq

# 1. write_fallback は output/posted_results_fallback/ に JSON を書く
with tempfile.TemporaryDirectory() as tmpdir:
    fallback_dir = Path(tmpdir) / "output" / "posted_results_fallback"

    mock_queue_row = {
        "queue_id": "q_test_001",
        "account_id": "night_scout",
        "status": "PROCESSING",
    }
    mock_text = "テスト投稿テキスト"

    with patch.object(ptq, "FALLBACK_DIR", fallback_dir):
        ptq.write_fallback(mock_queue_row, None, mock_text, None)

    files = list(fallback_dir.glob("*.json"))
    check("write_fallback が JSON ファイルを作成する", len(files) == 1)

    if files:
        content = json.loads(files[0].read_text(encoding="utf-8"))
        queue_data = content.get("queue", {})
        check("fallback JSON に queue.queue_id が含まれる", queue_data.get("queue_id") == "q_test_001")
        check("fallback JSON に queue.account_id が含まれる", queue_data.get("account_id") == "night_scout")

        # secret 系のキーが含まれないことを確認（トップレベル）
        secret_keys = {"access_token", "app_secret", "app_id", "password", "token"}
        found_secrets = [k for k in content if k.lower() in secret_keys]
        check("fallback JSON のトップレベルに secret キーが含まれない", len(found_secrets) == 0)

# 2. workflow に artifact upload ステップが含まれること
workflow_path = ROOT / ".github" / "workflows" / "threads-queue-worker.yml"
workflow_src = workflow_path.read_text(encoding="utf-8")
check("workflow に actions/upload-artifact が含まれる", "actions/upload-artifact" in workflow_src)
check("workflow に posted_results_fallback パスが含まれる", "posted_results_fallback" in workflow_src)
check("workflow に if: always() が含まれる", "if: always()" in workflow_src)
check("workflow に retention-days が含まれる", "retention-days" in workflow_src)

# 3. artifact 名に github.run_id が含まれること（ユニーク性）
check("artifact 名に github.run_id が含まれる", "github.run_id" in workflow_src)

# 4. fallback ディレクトリのパスが output/ 配下に限定されていること
check("fallback ディレクトリが output/ 配下", str(ptq.FALLBACK_DIR).endswith("posted_results_fallback"))

# 5. write_fallback は dry_run=True の場合に書かないこと
with tempfile.TemporaryDirectory() as tmpdir:
    fallback_dir2 = Path(tmpdir) / "output" / "posted_results_fallback"
    with patch.object(ptq, "FALLBACK_DIR", fallback_dir2):
        ptq.write_fallback(mock_queue_row, None, mock_text, None, dry_run=True)
    files2 = list(fallback_dir2.glob("*.json")) if fallback_dir2.exists() else []
    check("write_fallback(dry_run=True) はファイルを作成しない", len(files2) == 0)

print(f"\n--- 結果 ---")
print(f"PASS: {PASS_COUNT} / FAIL: {FAIL_COUNT}")
sys.exit(0 if FAIL_COUNT == 0 else 1)
