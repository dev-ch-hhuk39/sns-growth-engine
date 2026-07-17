#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
workflow_names = [
    "media-growth-production.yml",
    "media-growth-production-night-scout.yml",
    "media-growth-post-night-scout.yml",
    "media-growth-post-liver-manager.yml",
    "direct-reference-media-night-scout.yml",
    "direct-reference-media-liver-manager.yml",
]
texts = {name: (root / ".github/workflows" / name).read_text(encoding="utf-8") for name in workflow_names}
checks = [
    ("all media workflows run budget guard", all("check_media_resource_budget.py" in text for text in texts.values())),
    ("all posting workflows force fallback", all("FORCE_TEXT_ONLY_FALLBACK" in texts[name] for name in workflow_names[2:])),
    ("saved media posting uses post budget", all("--purpose post" in texts[name] for name in workflow_names[2:])),
    ("direct ingest has separate preparation budget", all("steps.preparation_budget.outcome == 'success'" in texts[name] for name in workflow_names[4:])),
    ("preparation skips when budget fails", all("steps.media_budget.outcome == 'success'" in texts[name] for name in workflow_names[:2])),
    ("night preparation never sudo installs", "sudo apt-get" not in texts["media-growth-production-night-scout.yml"]),
    ("cleanup is bounded workflow step", all("cleanup_media_workspace.py" in texts[name] for name in (workflow_names[0], workflow_names[1], workflow_names[4], workflow_names[5]))),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
