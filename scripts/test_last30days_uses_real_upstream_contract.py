#!/usr/bin/env python3
"""last30days integration must invoke the pinned script's actual CLI."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from src.reference.fetchers.last30days_fetcher import Last30DaysFetcher


payload = {
    "schema_version": "1.2",
    "source_status": {"reddit": "ok"},
    "clusters": [{"title": "配信の初見対応", "summary": "入りやすい配信が話題", "sources": ["reddit"], "engagement_total": 120}],
    "results": [{"candidate_id": "one", "title": "初見対応", "summary": "具体例", "cluster": 0, "source": "reddit"}],
}
fetcher = Last30DaysFetcher()
parsed = fetcher._extract_export("safe preamble\n" + json.dumps(payload, ensure_ascii=False) + "\n")
source = (ROOT / "src/reference/fetchers/last30days_fetcher.py").read_text(encoding="utf-8")
checks = [
    ("agent export parsed after preamble", parsed == payload),
    ("real emit flag", '"--emit=json"' in source),
    ("bounded result flag", '"--max-results"' in source),
    ("browser cookies disabled", '"--no-browser-cookies"' in source),
    ("fake trends subcommand absent", '"trends"' not in source.split("cmd = [", 1)[1].split("]", 1)[0]),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
