#!/usr/bin/env python3
"""Run a pinned standalone review component with the unchanged live libraries."""
import json
import os
from pathlib import Path
import sys

BUNDLE = Path(__file__).resolve().parents[1]
CURRENT = Path('/opt/github-runners/sns-growth-engine/.buffered-runtime/current')
sys.path[:0] = [str(BUNDLE / 'scripts'), str(CURRENT / 'src'), str(CURRENT / 'scripts')]
from sns_local_publication_review_job import run  # noqa: E402


def main() -> int:
    try:
        if os.environ.get('BUFFERED_POSTING_ENABLED') != 'false':
            raise RuntimeError('POSTING_OFF_REQUIRED')
        status, reports = run(base=BUNDLE)
        data = {'status': status, 'stages': reports, 'posts': 0,
                'paid_ai': 0, 'read_after_write': True}
    except Exception:
        data = {'status': 'BLOCKED', 'reason': 'REVIEW_COMPONENT_BLOCKED', 'posts': 0, 'paid_ai': 0}
    print('SNS_LOCAL_PUBLICATION_REVIEW=' + json.dumps(data, sort_keys=True))
    return 0 if data['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
