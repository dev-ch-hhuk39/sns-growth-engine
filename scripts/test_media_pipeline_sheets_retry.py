#!/usr/bin/env python3
import inspect

import discover_approved_source_videos as discovery
import run_media_growth_engine as growth
import run_media_production_pipeline as production
import transcribe_approved_source_videos as transcription
from sheets_client import SheetsClient

checks = [
    ("discovery retries Sheets", "_call_with_rate_limit_retry" in inspect.getsource(discovery.append_source_videos_to_sheets)),
    ("transcription retries Sheets load", "_call_with_rate_limit_retry" in inspect.getsource(transcription.load_rows)),
    ("clip generation retries Sheets", "_call_with_rate_limit_retry" in inspect.getsource(growth.append_clip_candidates_to_sheets)),
    ("production retries Sheets reads", "_call_with_rate_limit_retry" in inspect.getsource(production._records)),
    ("source video save retries Sheets", "_call_with_rate_limit_retry" in inspect.getsource(SheetsClient.save_source_video)),
    ("transcript save retries Sheets", "_call_with_rate_limit_retry" in inspect.getsource(SheetsClient.save_video_transcript)),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
