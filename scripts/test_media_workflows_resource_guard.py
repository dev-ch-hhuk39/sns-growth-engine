#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
workflow_names = [
    "direct-media-preparation.yml",
    "media-growth-production.yml",
    "media-growth-production-night-scout.yml",
    "media-growth-post-night-scout.yml",
    "media-growth-post-liver-manager.yml",
    "direct-reference-media-night-scout.yml",
    "direct-reference-media-liver-manager.yml",
]
texts = {name: (root / ".github/workflows" / name).read_text(encoding="utf-8") for name in workflow_names}
clip_workflow = (root / ".github/workflows/approved-source-clip-preparation.yml").read_text(encoding="utf-8")
clip_preparations = workflow_names[1:3]
posting_workflows = workflow_names[3:]
checks = [
    ("all media workflows run budget guard", all("check_media_resource_budget.py" in text for text in texts.values())),
    ("all posting workflows forbid text fallback", all("FORCE_TEXT_ONLY_FALLBACK" not in texts[name] for name in posting_workflows)),
    ("saved media posting uses post budget", all("--purpose post" in texts[name] for name in posting_workflows)),
    ("direct ingest has separate preparation budget", "steps.preparation_budget.outcome == 'success'" in texts["direct-media-preparation.yml"]),
    ("preparation skips when budget fails", all("steps.media_budget.outcome == 'success'" in texts[name] for name in clip_preparations)),
    ("night preparation installs only ffmpeg runtime", "sudo apt-get install --yes --no-install-recommends ffmpeg" in texts["media-growth-production-night-scout.yml"]),
    ("cleanup is bounded workflow step", all("cleanup_media_workspace.py" in texts[name] for name in ("direct-media-preparation.yml", *clip_preparations))),
    ("clip prep reclaims disposable caches before budget guard", clip_workflow.index("Inspect and reclaim disposable host caches") < clip_workflow.index("Check bounded preparation budget") and "docker builder prune --force --filter until=168h" in clip_workflow and "python3 -m pip cache purge" in clip_workflow),
    ("clip prep avoids deleting Docker images, containers, and volumes", all(command not in clip_workflow for command in ("docker system prune", "docker image prune", "docker volume prune", "docker container prune"))),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
