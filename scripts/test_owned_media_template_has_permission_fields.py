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
    "creator_name",
    "permission_source",
    "permission_evidence_url_or_file",
    "permission_date",
    "permission_expire_date",
    "rights_status",
    "allowed_uses",
    "prohibited_uses",
    "target_account_id",
    "notes",
    "reviewed_by",
    "reviewed_at",
}
example = data.get("example", {})
allowed_uses = example.get("allowed_uses", {})
checks = [
    ("template exists", path.exists()),
    ("required listed", required.issubset(set(data.get("required_fields", [])))),
    ("example fields", required.issubset(set(example.keys()))),
    ("allowed uses fields", {"save", "cut", "upload", "repost", "derivative_post", "paid_ad", "organic_post"}.issubset(set(allowed_uses.keys()))),
    ("approved statuses", {"owned", "licensed", "approved_creator_clip"}.issubset(set(data.get("allowed_rights_status", [])))),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
