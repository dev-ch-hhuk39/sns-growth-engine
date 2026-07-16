#!/usr/bin/env python3
import os
import tempfile
import time
from pathlib import Path

from cleanup_media_workspace import build_cleanup_plan

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    transient = root / "downloads"
    clips = root / "clips"
    outside = root / "outside"
    for directory in (transient, clips, outside):
        directory.mkdir()
    old_transient = transient / "failed.mp4"
    old_clip = clips / "published.mp4"
    old_outside = outside / "keep.mp4"
    for path in (old_transient, old_clip, old_outside):
        path.write_bytes(b"x")
        os.utime(path, (time.time() - 40 * 86400, time.time() - 40 * 86400))
    plan = build_cleanup_plan(
        delete_roots=[transient],
        audit_root=clips,
        config={"resource_limits": {"failed_media_retention_days": 7, "processed_asset_audit_days": 30}},
    )
    delete_paths = {row["path"] for row in plan["delete_candidates"]}
    audit_paths = {row["path"] for row in plan["audit_candidates"]}
    checks = [
        ("transient candidate bounded", str(old_transient) in delete_paths),
        ("processed clip audit only", str(old_clip) in audit_paths and str(old_clip) not in delete_paths),
        ("outside path untouched", str(old_outside) not in delete_paths and str(old_outside) not in audit_paths),
        ("dry plan deletes nothing", old_transient.exists() and old_clip.exists()),
    ]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
