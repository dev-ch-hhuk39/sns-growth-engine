#!/usr/bin/env python3

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

path = ROOT / "scripts" / "ingest_direct_reference_media.py"
spec = importlib.util.spec_from_file_location("direct_media_core_bundle_test", path)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

rows = [
    {
        "source_post_id": "sp_target",
        "source_post_media_id": "spm_1",
        "media_index": "1",
    },
    {
        "source_post_id": "sp_other",
        "source_post_media_id": "spm_other",
        "media_index": "0",
    },
    {
        "source_post_id": "sp_target",
        "source_post_media_id": "spm_0",
        "media_index": "0",
    },
]

labels = []

class Worksheet:
    def get_all_records(self):
        return list(rows)

class Client:
    def _ws(self, logical_name):
        assert logical_name == "source_post_media"
        return Worksheet()

    def _call_with_rate_limit_retry(self, label, fn):
        labels.append(label)
        return fn()

bundle = module.source_post_media_bundle(Client(), "sp_target")

assert labels == ["read_source_post_media_bundle"]
assert [row["source_post_media_id"] for row in bundle] == ["spm_0", "spm_1"]

print("[OK] parent bundle read uses bounded Sheets retry and preserves order")
