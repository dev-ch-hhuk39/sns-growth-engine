#!/usr/bin/env python3
"""Self-hosted posting workflows must not reuse a stale runner checkout."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = [
    "autonomous-growth-loop-night-scout.yml",
    "autonomous-growth-loop-liver-manager.yml",
    "direct-reference-media-night-scout.yml",
    "direct-reference-media-liver-manager.yml",
    "media-growth-post-liver-manager.yml",
]


def main() -> int:
    failures = 0
    for workflow in WORKFLOWS:
        text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        ok = (
            "Verify triggering revision" in text
            and "ref: ${{ github.sha }}" in text
            and 'git checkout --detach "$GITHUB_SHA"' in text
        )
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'} {workflow} pins the triggering SHA")
    print(f"PASS: {len(WORKFLOWS) - failures} / FAIL: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
