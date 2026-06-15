#!/usr/bin/env python3
"""test_phase13_pipeline_store.py"""
from __future__ import annotations
import os, sys, tempfile, json
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"  {'✓' if condition else '✗'} [{status}] {name}" + (f": {detail}" if detail else ""))


def main():
    print("=== Phase 13: PipelineStore テスト ===\n")

    print("[1] Import")
    try:
        from src.storage.pipeline_store import PipelineStore
        check("import OK", True)
    except Exception as e:
        check("import", False, str(e))
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpdir:
        print("\n[2] インスタンス化")
        store = PipelineStore(output_dir=tmpdir)
        check("PipelineStore instantiated", store is not None)

        print("\n[3] save (dry_run=True) — 実ファイルを書かない")
        result_path = store.save("RUN_001", "fetch", {"items": [1, 2]}, dry_run=True)
        check("returns path string", isinstance(result_path, str))
        # dry_run では実ファイルは作成されない
        check("dry_run: file NOT written", not os.path.exists(result_path))

        print("\n[4] save (dry_run=False) — 実ファイルを書く")
        result_path2 = store.save("RUN_001", "fetch", {"items": [1, 2]}, dry_run=False)
        check("returns path string", isinstance(result_path2, str))
        check("file exists after real save", os.path.exists(result_path2))

        print("\n[5] load")
        loaded = store.load("RUN_001", "fetch")
        check("loaded is dict", isinstance(loaded, dict))
        check("items preserved", loaded.get("items") == [1, 2])

        print("\n[6] save_summary")
        summary_path = store.save_summary(
            "RUN_001",
            {"status": "OK", "posted": 2, "failed": 0},
            dry_run=False,
        )
        check("summary_path is string", isinstance(summary_path, str))
        check("summary file exists", os.path.exists(summary_path))

        print("\n[7] list_runs")
        runs = store.list_runs()
        check("list_runs returns list", isinstance(runs, list))
        check("RUN_001 in list", "RUN_001" in runs)

        print("\n[8] 複数 run_id")
        store.save("RUN_002", "generate", {"drafts": 3}, dry_run=False)
        store.save("RUN_003", "publish", {"posted": 1}, dry_run=False)
        runs2 = store.list_runs()
        check("3件以上のruns", len(runs2) >= 3)

        print("\n[9] load 存在しないキー → None or KeyError handled")
        missing = store.load("RUN_999", "nonexistent")
        check("missing returns None", missing is None)

        print("\n[10] save は run_id ディレクトリを作成する")
        store.save("RUN_NESTED", "step1", {"ok": True}, dry_run=False)
        run_dir = os.path.join(tmpdir, "RUN_NESTED")
        check("run directory created", os.path.isdir(run_dir))

    print("\n--- 結果 ---")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"PASS: {passed} / FAIL: {failed}")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
