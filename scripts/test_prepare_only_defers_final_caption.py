#!/usr/bin/env python3
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'scripts' / 'run_media_production_pipeline.py').read_text(encoding='utf-8')
execute_start = source.index('\ndef execute(')
main_start = source.index('\ndef main()', execute_start)
body = source[execute_start:main_start]
media_persist = body.index('if media_id not in existing_media_ids:')
prepare = body.index('if plan.get("prepare_only"):', media_persist)
caption = body.index('caption = _generate_final_media_caption(', prepare)
queue = body.index('queue_id = f"media_q_{clip_id}"', caption)
checks = [
    ('asset persists before prepare completion', media_persist < prepare),
    ('prepare completes before final caption', prepare < caption),
    ('final caption remains before posting queue', caption < queue),
    ('prepare explicitly defers final caption', 'DEFERRED_UNTIL_POST' in body[prepare:caption]),
    ('prepare block creates no queue', 'queue_id = f"media_q_{clip_id}"' not in body[prepare:caption]),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
