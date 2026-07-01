#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts/generate_threads_ideas_from_references.py")
gen = importlib.util.module_from_spec(spec); spec.loader.exec_module(gen)
candidate = gen.build_rewritten_post_candidate(
    account_id="night_scout",
    original_text="今日のメイクと出勤準備を紹介します。お気に入りのリップも見てね。",
    generated_text="夜職を始める前に不安を整理する投稿。店選び、生活リズム、相談先の順に自分の状況を確認する。",
    transformation_type="structure_reference",
)
checks = [("waiting review", candidate["status"] == "WAITING_REVIEW"), ("not auto", candidate["auto_publish"] is False), ("type", candidate["transformation_type"] == "structure_reference")]
bad = [n for n, ok in checks if not ok]
for n, ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
