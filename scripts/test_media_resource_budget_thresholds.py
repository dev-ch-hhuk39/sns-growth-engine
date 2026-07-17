#!/usr/bin/env python3
from collections import namedtuple

from check_media_resource_budget import build_report

Disk = namedtuple("Disk", "total used free")
config = {"resource_limits": {"disk_prepare_stop_percent": 80, "disk_text_only_percent": 90, "cloudinary_text_only_percent": 85}}

checks = [
    ("normal budget passes", build_report(config=config, disk_usage=Disk(100, 40, 60))["status"] == "PASS"),
    ("80 percent blocks preparation", build_report(config=config, disk_usage=Disk(100, 80, 20))["status"] == "PREPARATION_BLOCKED"),
    ("80 percent still permits saved media post", build_report(config=config, disk_usage=Disk(100, 80, 20))["media_post_allowed"] is True),
    ("80 percent blocks new media preparation", build_report(config=config, disk_usage=Disk(100, 80, 20))["preparation_allowed"] is False),
    ("90 percent forces text only", build_report(config=config, disk_usage=Disk(100, 90, 10))["status"] == "TEXT_ONLY"),
    ("90 percent blocks saved media post", build_report(config=config, disk_usage=Disk(100, 90, 10))["media_post_allowed"] is False),
    ("cloudinary threshold forces text only", build_report(config=config, disk_usage=Disk(100, 40, 60), cloudinary={"status": "AVAILABLE", "usage_percent": 85})["status"] == "TEXT_ONLY"),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
