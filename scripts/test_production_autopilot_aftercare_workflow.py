#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

workflow = (
    ROOT
    / ".github/workflows/"
    "production-autopilot-aftercare.yml"
).read_text(
    encoding="utf-8"
)

checks = [
    (
        "workflow has schedule",
        (
            "schedule:" in workflow
            and 'cron: "40 14 * * *"'
            in workflow
        ),
    ),
    (
        "workflow dispatch exists",
        (
            "workflow_dispatch:"
            in workflow
            and "confirm_aftercare"
            in workflow
        ),
    ),
    (
        "publish disabled globally",
        (
            'PUBLISH_ENABLED: "false"'
            in workflow
        ),
    ),
    (
        "threads real post disabled",
        (
            'ALLOW_REAL_THREADS_POST: "false"'
            in workflow
        ),
    ),
    (
        "x disabled",
        (
            'ALLOW_REAL_X_POST: "false"'
            in workflow
        ),
    ),
    (
        "media post disabled",
        (
            'ALLOW_MEDIA_POSTS: "false"'
            in workflow
            and (
                'ALLOW_REAL_THREADS_VIDEO_POST: '
                '"false"'
                in workflow
            )
        ),
    ),
    (
        "download cut upload disabled",
        (
            'ALLOW_VIDEO_DOWNLOAD: "false"'
            in workflow
            and 'ALLOW_VIDEO_CUT: "false"'
            in workflow
            and (
                'ALLOW_CLOUDINARY_UPLOAD: '
                '"false"'
                in workflow
            )
        ),
    ),
    (
        "transcription disabled",
        (
            'ALLOW_TRANSCRIPTION_API: "false"'
            in workflow
        ),
    ),
    (
        "account metric tokens wired",
        (
            "THREADS_ACCESS_TOKEN_"
            "NIGHT_SCOUT"
            in workflow
            and (
                "THREADS_ACCESS_TOKEN_"
                "LIVER_MANAGER"
                in workflow
            )
            and (
                "THREADS_ACCESS_TOKEN_"
                "BEAUTY_ACCOUNT"
                in workflow
            )
        ),
    ),
    (
        "due metric worker applies",
        (
            "process_threads_metric_jobs.py"
            in workflow
            and "--confirm-metrics"
            in workflow
            and "--use-sheets"
            in workflow
            and "--max-jobs 20"
            in workflow
        ),
    ),
    (
        "aftercare breaks activation cycle",
        (
            "production_publish_activation_"
            "approved=false"
            not in workflow
        ),
    ),
    (
        "pdca uses bounded READY maintenance",
        (
            "maintain_text_ready_inventory.py"
            in workflow
            and "--account-id all"
            in workflow
            and (
                "--confirm-ready-maintenance"
                in workflow
            )
            and "--slot-id activation_pdca" not in workflow
        ),
    ),
    (
        "scheduled aftercare applies",
        (
            'if [ "${{ github.event_name }}" '
            '= "schedule" ]'
            in workflow
            and "AFTERCARE_APPLY=$apply"
            in workflow
        ),
    ),
    (
        "measured attribution applies",
        (
            "run_growth_attribution_cycle.py"
            in workflow
            and "--confirm-attribution"
            in workflow
        ),
    ),
    (
        "media discovery delegated",
        (
            "discover_approved_source_videos.py"
            not in workflow
            and "--confirm-discovery"
            not in workflow
        ),
    ),
    (
        "aftercare does not fetch media",
        "--fetch-real" not in workflow,
    ),
    (
        "source registry sync step",
        (
            "seed_source_registry.py"
            in workflow
            and "--confirm-seed"
            in workflow
        ),
    ),
    (
        "source registry setup bounded",
        "--skip-setup" in workflow,
    ),
    (
        "media growth delegated",
        (
            "run_media_growth_engine.py"
            not in workflow
            and "--confirm-media-growth"
            not in workflow
        ),
    ),
    (
        "no real post command",
        "--confirm-real-post"
        not in workflow,
    ),
    (
        "no upload download cut confirm",
        (
            "--confirm-upload"
            not in workflow
            and "--confirm-download"
            not in workflow
            and "--confirm-cut"
            not in workflow
        ),
    ),
]

failed = [
    name
    for name, ok in checks
    if not ok
]

for name, ok in checks:
    print(
        f"  {'PASS' if ok else 'FAIL'} "
        f"{name}"
    )

print(
    f"PASS: {len(checks) - len(failed)} "
    f"/ FAIL: {len(failed)}"
)

raise SystemExit(
    1 if failed else 0
)
