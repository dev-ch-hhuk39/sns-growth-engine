#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.x_exact_status import validate_exact_status_provenance  # noqa: E402

manifest = json.loads((ROOT / "config/physical_media_goldens.json").read_text(encoding="utf-8"))
checks: dict[str, bool] = {}
for item in manifest["x_exact_statuses"]:
    status_id = item["url"].rstrip("/").rsplit("/", 1)[-1]
    metadata = {
        "id": f"media-{status_id}",
        "display_id": status_id,
        "webpage_url": item["url"],
        "uploader_id": item["source_handle"].lstrip("@"),
        "formats": [{"vcodec": "h264"}],
    }
    result = validate_exact_status_provenance(item["url"], item, metadata)
    checks[f"exact source passes {item['source_handle']}"] = result["status"] == "PASS" and result["canonical_url"] == item["url"]
    quote = validate_exact_status_provenance(item["url"], item, {**metadata, "is_quote_status": True})
    checks[f"quote blocked {item['source_handle']}"] = quote["status"] == "BLOCKED"
    wrong_status = validate_exact_status_provenance(
        item["url"], item, {**metadata, "display_id": "9999999999999999999"}
    )
    checks[f"status mismatch blocked {item['source_handle']}"] = (
        wrong_status["status"] == "BLOCKED"
        and "extracted_status_id_mismatch" in wrong_status["reasons"]
    )
checks["profile URL blocked"] = validate_exact_status_provenance("https://x.com/3j2c9q", {"source_handle": "@3j2c9q"}, {"formats": [{"vcodec": "h264"}]})["status"] == "BLOCKED"
checks["author mismatch blocked"] = validate_exact_status_provenance("https://x.com/other/status/1", {"source_handle": "@3j2c9q"}, {"uploader_id": "other", "formats": [{"vcodec": "h264"}]})["status"] == "BLOCKED"
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
