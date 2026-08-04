#!/usr/bin/env python3
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import download_approved_media as module
with tempfile.TemporaryDirectory() as tmp:
    local = Path(tmp) / 'source.mp4'
    local.write_bytes(b'verified-video-fixture')
    original_probe = module.probe_video_file
    module.probe_video_file = lambda _path: {
        'media_probe_status': 'PASS', 'video_stream_count': 1,
        'audio_stream_count': 1, 'duration_seconds': 120,
        'width': 1920, 'height': 1080, 'aspect_ratio': '16:9',
    }
    original_env = os.environ.get('ALLOW_VIDEO_DOWNLOAD')
    os.environ['ALLOW_VIDEO_DOWNLOAD'] = 'true'
    try:
        args = SimpleNamespace(
            source_video_id='sv_existing',
            source_video_row={
                'source_video_id': 'sv_existing',
                'canonical_video_url': 'https://www.youtube.com/watch?v=abcdefghijk',
                'rights_status': 'approved_creator_clip',
                'download_status': 'DOWNLOADED',
                'local_path': str(local),
            },
            source_videos_json='', source_url='',
            rights_status='approved_creator_clip',
            download=True, confirm_download=True, dry_run=False,
        )
        plan = module.build_download_plan(args)
        result = module.execute_download(plan)
    finally:
        module.probe_video_file = original_probe
        if original_env is None:
            os.environ.pop('ALLOW_VIDEO_DOWNLOAD', None)
        else:
            os.environ['ALLOW_VIDEO_DOWNLOAD'] = original_env
checks = [
    ('verified existing download is reused', plan['status'] == 'DOWNLOADED'),
    ('reuse does not redownload', plan['would_download'] is False),
    ('reuse keeps exact local path', plan['download_result']['local_path'] == str(local)),
    ('execute preserves reused result', result['download_result'].get('reused_existing_download') is True),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
