#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts/generate_threads_ideas_from_references.py")
gen = importlib.util.module_from_spec(spec); spec.loader.exec_module(gen)
text = "配信が続く人は才能より先に仕組みを作っている。毎日同じ時間に始めることが大事。"
candidate = gen.build_rewritten_post_candidate(account_id="liver_manager", original_text=text, generated_text=text, transformation_type="structure_reference")
checks = [("blocked", candidate["status"] == "BLOCKED"), ("no generated text", candidate["generated_text"] == "")]
bad = [n for n, ok in checks if not ok]
for n, ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
