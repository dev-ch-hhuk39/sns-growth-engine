#!/usr/bin/env python3
import importlib.util
from pathlib import Path

path = Path(__file__).with_name("import_owned_canary_assets.py")
spec = importlib.util.spec_from_file_location("owned_import", path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
base = {"asset_id": "owned_ns_001", "source_group_id": "owned_ns_001", "account_id": "night_scout", "asset_purpose": "direct_image", "local_path": str(Path(__file__).resolve()), "https_url": "", "rights_status": "owned", "owner_declaration": "Owner declaration", "threads_post_allowed": True, "cloudinary_storage_allowed": True, "allowed_operations": ["direct"], "media_order": 0, "public_post_text": "夜職を始める前に、条件だけでなく続けやすさも一度整理しておくと安心です。"}
plan = module.build_plan({"schema_version": 1, "assets": [base]})
assert plan["status"] == "PLAN_ONLY", plan
bad = dict(base); bad["rights_status"] = "unknown"
assert module.build_plan({"schema_version": 1, "assets": [bad]})["status"] == "BLOCKED"
bad = dict(base); bad["https_url"] = "https://example.test/a.jpg"; bad["local_path"] = ""
assert module.build_plan({"schema_version": 1, "assets": [bad]})["status"] == "BLOCKED"
print("PASS")
