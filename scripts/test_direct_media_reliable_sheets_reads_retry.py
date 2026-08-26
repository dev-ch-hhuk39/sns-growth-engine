#!/usr/bin/env python3

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

path = ROOT / "scripts" / "ingest_direct_reference_media_reliable.py"
spec = importlib.util.spec_from_file_location("direct_media_reliable_retry_test", path)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

labels = []

class Worksheet:
    def get_all_records(self):
        return [{"source_post_id": "sp_test"}]

class Client:
    def _ws(self, logical_name):
        assert logical_name == "source_posts"
        return Worksheet()

    def _call_with_rate_limit_retry(self, label, fn):
        labels.append(label)
        return fn()

records = module._records_with_sheet_retry(Client(), "source_posts")

assert records == [{"source_post_id": "sp_test"}]
assert labels == ["read_all_records:source_posts"]

print("[OK] reliable selector Sheets reads use bounded retry")
