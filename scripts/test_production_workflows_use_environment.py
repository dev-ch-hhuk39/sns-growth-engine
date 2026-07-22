#!/usr/bin/env python3
"""Production jobs are isolated by the GitHub production Environment."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

production = [
    "account-acquisition.yml",
    "autonomous-growth-loop-liver-manager.yml",
    "autonomous-growth-loop-night-scout.yml",
    "autonomous-growth-loop.yml",
    "autopilot-auto-ready.yml",
    "content-pilot-publish.yml",
    "content-slot-recovery.yml",
    "direct-media-preparation.yml",
    "direct-reference-media-liver-manager.yml",
    "direct-reference-media-night-scout.yml",
    "media-approved-pilot.yml",
    "media-growth-post-liver-manager.yml",
    "media-growth-post-night-scout.yml",
    "media-growth-production-night-scout.yml",
    "media-growth-production.yml",
    "media-transcription-production.yml",
    "production-autopilot-aftercare.yml",
    "refresh-threads-tokens.yml",
    "source-research.yml",
    "threads-queue-worker.yml",
]
diagnostic = [
    "ci.yml",
    "content-daily-dry-run.yml",
    "source-fetch-dry-run.yml",
    "v2-dry-run-check.yml",
    "video-reference-dry-run.yml",
]

checks = []
for name in production:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    checks.append((f"{name}: production environment", "    environment: production" in text))
    checks.append((f"{name}: standard runner", "runs-on: ubuntu-latest" in text and "self-hosted" not in text))
for name in diagnostic:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    checks.append((f"{name}: no production environment", "environment: production" not in text))

for label, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {label}")
print(f"PASS: {sum(ok for _, ok in checks)} / FAIL: {sum(not ok for _, ok in checks)}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
