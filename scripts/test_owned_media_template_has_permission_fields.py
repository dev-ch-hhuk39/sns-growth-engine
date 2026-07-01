#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "config/source_accounts/owned_media_asset_template.json"
data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
required = {
    "asset_id",
    "platform",
    "source_url",
    "local_file_ref",
    "owner_name",
    "permission_source",
    "permission_date",
    "rights_status",
    "allowed_uses",
    "expires_at",
    "target_account_id",
    "notes",
}
example = data.get("example", {})
allowed_uses = example.get("allowed_uses", {})
checks = [
    ("template exists", path.exists()),
    ("required listed", required.issubset(set(data.get("required_fields", [])))),
    ("example fields", required.issubset(set(example.keys()))),
    ("allowed uses fields", {"cut", "upload", "repost", "derivative_post"}.issubset(set(allowed_uses.keys()))),
    ("approved statuses", {"owned", "licensed", "approved_creator_clip"}.issubset(set(data.get("allowed_rights_status", [])))),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
