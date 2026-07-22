#!/usr/bin/env python3
import inspect

import run_media_growth_engine as engine

build = inspect.getsource(engine.build_media_growth_plan)
main = inspect.getsource(engine.main)
checks = [
    ("transcript rows reduced to status metadata", '"transcript_text_redacted_preview"' not in build),
    ("top clips omit transcript excerpt", '"transcript_excerpt": row.get' not in build),
    ("all candidates kept only in private plan key", '"_clip_candidates_for_save": clip_candidates' in build),
    ("private candidate rows removed before stdout", 'plan.pop("_clip_candidates_for_save", None)' in main),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
