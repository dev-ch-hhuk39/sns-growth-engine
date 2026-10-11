#!/usr/bin/env python3
"""Bounded, nonpublishing SNS runtime and Sheets-readiness health check."""
from __future__ import annotations
import argparse
import os
import re
import shlex
import stat
import subprocess
import time
from pathlib import Path

SHA = re.compile(r'[0-9a-f]{40}\Z')


def health_probe(release: Path, revision: str, env_file: Path, *, check_sheets: bool = True,
                 runner=subprocess.run, attempts: int = 2, retry_delay: float = 4) -> bool:
    if not SHA.fullmatch(revision) or not release.is_dir() or release.is_symlink():
        raise ValueError('invalid_release_identity')
    if release.name != revision or (release / '.production-release').read_text().strip() != revision:
        raise ValueError('release_revision_mismatch')
    python = release / '.venv/bin/python'
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError('release_python_missing')
    if not env_file.is_file() or env_file.is_symlink() or stat.S_IMODE(env_file.stat().st_mode) != 0o600:
        raise ValueError('untrusted_environment_file')
    child_env = dict(os.environ)
    for raw in env_file.read_text(encoding='utf-8').splitlines():
        if not raw.strip():
            continue
        tokens = shlex.split(raw)
        if len(tokens) != 1 or '=' not in tokens[0]:
            raise ValueError('invalid_environment_entry')
        key, value = tokens[0].split('=', 1)
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
            raise ValueError('invalid_environment_key')
        child_env[key] = value
    # Disable every action gate regardless of the candidate's intended posting mode.
    for key in ('PUBLISH_ENABLED', 'ALLOW_REAL_THREADS_POST', 'ALLOW_REAL_THREADS_VIDEO_POST',
                'ALLOW_MEDIA_POSTS', 'ALLOW_CLOUDINARY_UPLOAD', 'ALLOW_VIDEO_DOWNLOAD',
                'ALLOW_VIDEO_CUT', 'ALLOW_REAL_X_POST', 'GITHUB_MODELS_ENABLED'):
        child_env[key] = 'false'
    child_env['PYTHONDONTWRITEBYTECODE'] = '1'
    child_env['PYTHONPATH'] = os.pathsep.join((str(release / 'scripts'), str(release / 'src')))
    script = '''from importlib import metadata
for name in ('cloudinary', 'faster-whisper', 'yt-dlp', 'playwright'):
    assert metadata.version(name)
from config_loader import get_config
from sheets_client import SheetsClient
cfg=get_config()
assert cfg.get('sheet_id') and cfg.get('sa_dict')
'''
    if check_sheets:
        script += '''client=SheetsClient(cfg['sheet_id'], cfg['sa_dict'], dry_run=True)
assert len(client._sh.worksheets()) > 0
'''
    for number in range(attempts):
        try:
            result = runner([str(python), '-B', '-c', script], cwd=release, env=child_env,
                            capture_output=True, text=True, timeout=85, check=False)
            if result.returncode == 0:
                return True
        except subprocess.TimeoutExpired:
            pass
        if number + 1 < attempts:
            time.sleep(retry_delay)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--env-file', type=Path, required=True)
    args = parser.parse_args()
    try:
        success = health_probe(args.release, args.revision, args.env_file)
    except (ValueError, OSError, shlex.Error) as exc:
        print('[BLOCKED] candidate health:', type(exc).__name__)
        return 78
    print('[OK] runtime dependencies and read-only Sheets health' if success else
          '[BLOCKED] bounded runtime health check failed')
    return 0 if success else 78


if __name__ == '__main__':
    raise SystemExit(main())
