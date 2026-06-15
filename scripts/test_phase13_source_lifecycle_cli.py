#!/usr/bin/env python3
"""test_phase13_source_lifecycle_cli.py"""
from __future__ import annotations
import json, os, sys, subprocess, tempfile
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"  {'✓' if condition else '✗'} [{status}] {name}" + (f": {detail}" if detail else ""))


def _run(cmd: list[str]) -> tuple[int, str, str]:
    r = subprocess.run(
        [sys.executable] + cmd,
        capture_output=True, text=True,
        cwd=_ROOT,
    )
    return r.returncode, r.stdout, r.stderr


def _sample_sources() -> dict:
    return {
        "sources": [
            {
                "source_id": "src_test_x_001",
                "source_platform": "x",
                "source_url": "https://x.com/test_handle",
                "source_handle": "@test_handle",
                "target_account_ids": ["night_scout"],
                "collection_method": "agent_reach",
                "candidate_status": "candidate",
                "active": False,
                "fetch_enabled": False,
                "allow_network_fetch": False,
                "rights_policy": "reference_only",
                "reuse_policy": "reference_only",
                "media_policy": "plan_only",
                "max_items_per_run": 10,
                "review_notes": "test",
                "created_at": "2026-06-15T00:00:00+09:00",
                "updated_at": "2026-06-15T00:00:00+09:00",
            }
        ]
    }


def main():
    print("=== Phase 13: Source Lifecycle CLI テスト ===\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        src_file = os.path.join(tmpdir, "test_sources.json")

        print("[1] add_source_candidate.py — dry_run (デフォルト)")
        with open(src_file, "w", encoding="utf-8") as f:
            json.dump({"sources": []}, f)

        code, out, err = _run([
            "scripts/add_source_candidate.py",
            "--source-file", src_file,
            "--source-id", "src_ns_x_new_001",
            "--platform", "x",
            "--url", "https://x.com/test_new",
            "--handle", "@test_new",
            "--target-account", "night_scout",
            "--collection-method", "agent_reach",
        ])
        check("exit_code=0 (dry_run)", code == 0, f"code={code} err={err[:100]}")
        check("DRY_RUN in stdout", "DRY_RUN" in out)
        # dry_run なのでファイルは変更されない
        with open(src_file, encoding="utf-8") as f:
            saved = json.load(f)
        check("dry_run: ファイル未変更 (0件のまま)", len(saved.get("sources", [])) == 0)

        print("\n[2] add_source_candidate.py — --no-dry-run で実書き込み")
        code2, out2, err2 = _run([
            "scripts/add_source_candidate.py",
            "--source-file", src_file,
            "--source-id", "src_ns_x_new_001",
            "--platform", "x",
            "--url", "https://x.com/test_new",
            "--handle", "@test_new",
            "--target-account", "night_scout",
            "--collection-method", "agent_reach",
            "--no-dry-run",
        ])
        check("exit_code=0 (no-dry-run)", code2 == 0, f"code={code2} err={err2[:100]}")
        with open(src_file, encoding="utf-8") as f:
            saved2 = json.load(f)
        check("no-dry-run: 1件追加された", len(saved2.get("sources", [])) == 1)
        check("source_id 正しい", saved2["sources"][0]["source_id"] == "src_ns_x_new_001")
        check("active=False", saved2["sources"][0].get("active") is False)
        check("fetch_enabled=False", saved2["sources"][0].get("fetch_enabled") is False)
        check("candidate_status=candidate", saved2["sources"][0].get("candidate_status") == "candidate")

        print("\n[3] add_source_candidate.py — 重複 source_id → エラー")
        code3, out3, err3 = _run([
            "scripts/add_source_candidate.py",
            "--source-file", src_file,
            "--source-id", "src_ns_x_new_001",
            "--platform", "x",
            "--url", "https://x.com/dup",
            "--handle", "@dup",
            "--target-account", "night_scout",
            "--collection-method", "agent_reach",
            "--no-dry-run",
        ])
        check("重複 source_id: exit_code=1", code3 == 1, f"code={code3}")
        check("ERROR in stdout", "ERROR" in out3 or "ERROR" in err3)

        print("\n[4] update_source_status.py — dry_run")
        src_file2 = os.path.join(tmpdir, "test_sources2.json")
        with open(src_file2, "w", encoding="utf-8") as f:
            json.dump(_sample_sources(), f)

        code4, out4, err4 = _run([
            "scripts/update_source_status.py",
            "--source-file", src_file2,
            "--source-id", "src_test_x_001",
            "--status", "waiting_review",
        ])
        check("update dry_run: exit_code=0", code4 == 0, f"code={code4} err={err4[:100]}")
        check("DRY_RUN in stdout", "DRY_RUN" in out4)
        with open(src_file2, encoding="utf-8") as f:
            saved4 = json.load(f)
        check("dry_run: status 未変更 (candidate のまま)",
              saved4["sources"][0].get("candidate_status") == "candidate")

        print("\n[5] update_source_status.py — --no-dry-run で実変更")
        code5, out5, err5 = _run([
            "scripts/update_source_status.py",
            "--source-file", src_file2,
            "--source-id", "src_test_x_001",
            "--status", "waiting_review",
            "--no-dry-run",
        ])
        check("update no-dry-run: exit_code=0", code5 == 0, f"code={code5} err={err5[:100]}")
        with open(src_file2, encoding="utf-8") as f:
            saved5 = json.load(f)
        check("status が waiting_review に更新された",
              saved5["sources"][0].get("candidate_status") == "waiting_review")

        print("\n[6] update_source_status.py — fetch_enabled without --allow-fetch → BLOCKED")
        code6, out6, err6 = _run([
            "scripts/update_source_status.py",
            "--source-file", src_file2,
            "--source-id", "src_test_x_001",
            "--fetch-enabled",
            "--no-dry-run",
        ])
        check("fetch_enabled without allow-fetch: exit_code=1", code6 == 1, f"code={code6}")
        check("BLOCKED in stdout", "BLOCKED" in out6 or "BLOCKED" in err6)

        print("\n[7] review_source_candidates.py — 基本動作")
        src_file3 = os.path.join(_ROOT, "config", "source_accounts", "production_sources.example.json")
        if os.path.isfile(src_file3):
            code7, out7, err7 = _run([
                "scripts/review_source_candidates.py",
                "--source-file", src_file3,
                "--account", "night_scout",
            ])
            check("review exit_code=0", code7 == 0, f"code={code7} err={err7[:100]}")
            check("night_scout in stdout", "night_scout" in out7)
            check("candidate in stdout", "candidate" in out7)
        else:
            check("production_sources.example.json 存在", False, "ファイルなし")

        print("\n[8] review_source_candidates.py — --status disabled フィルタ")
        if os.path.isfile(src_file3):
            code8, out8, _ = _run([
                "scripts/review_source_candidates.py",
                "--source-file", src_file3,
                "--status", "disabled",
            ])
            check("disabled filter exit_code=0", code8 == 0)
            check("disabled in stdout", "disabled" in out8)

    print("\n--- 結果 ---")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"PASS: {passed} / FAIL: {failed}")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
