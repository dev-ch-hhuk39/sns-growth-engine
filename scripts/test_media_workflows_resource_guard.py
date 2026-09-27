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
hosted_clip_job = texts["direct-media-preparation.yml"].split("  refill-existing-approved-clips:", 1)[-1]
clip_preparations = workflow_names[1:3]
posting_workflows = workflow_names[3:]
checks = [
    ("all media workflows run budget guard", all("check_media_resource_budget.py" in text for text in texts.values())),
    ("all posting workflows forbid text fallback", all("FORCE_TEXT_ONLY_FALLBACK" not in texts[name] for name in posting_workflows)),
    ("saved media posting uses post budget", all("--purpose post" in texts[name] for name in posting_workflows)),
    ("direct ingest has separate preparation budget", "steps.preparation_budget.outcome == 'success'" in texts["direct-media-preparation.yml"]),
    ("stored-source clip fallback runs on an independent hosted runner", "runs-on: ubuntu-latest" in hosted_clip_job and "--stored-source-only" in hosted_clip_job),
    ("hosted clip fallback enforces its own runner budget", "check_media_resource_budget.py" in hosted_clip_job and "--purpose prepare" in hosted_clip_job),
    ("hosted clip fallback never enables publishing", all(f'{name}: "false"' in hosted_clip_job for name in ("PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_THREADS_VIDEO_POST", "ALLOW_MEDIA_POSTS"))),
    ("preparation skips when budget fails", all("steps.media_budget.outcome == 'success'" in texts[name] for name in clip_preparations)),
    ("night preparation installs only ffmpeg runtime", "sudo apt-get install --yes --no-install-recommends ffmpeg" in texts["media-growth-production-night-scout.yml"]),
    ("fallback cleanups are restricted to owned run workspaces", all(".sns-media-prep-owned" in text and "shutil.rmtree(workspace)" in text for text in (texts["direct-media-preparation.yml"], clip_workflow))),
    ("clip prep does not clear shared runner caches", all(command not in clip_workflow for command in ("docker builder prune", "pip cache purge", "docker system prune"))),
    ("clip prep avoids deleting Docker images, containers, and volumes", all(command not in clip_workflow for command in ("docker system prune", "docker image prune", "docker volume prune", "docker container prune"))),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
