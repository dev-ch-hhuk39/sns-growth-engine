#!/usr/bin/env python3
"""Write a 0600 candidate-only SNS runtime environment; never overwrite live."""
from __future__ import annotations
import argparse
import os
import shlex
import subprocess
from pathlib import Path

KEYS = (
    'GCP_SA_JSON_BASE64', 'SA_JSON_BASE64', 'SPREADSHEET_ID', 'SNS_MASTER_SHEET_ID',
    'THREADS_ACCESS_TOKEN_NIGHT_SCOUT', 'THREADS_USER_ID_NIGHT_SCOUT', 'THREADS_HANDLE_NIGHT_SCOUT',
    'THREADS_ACCESS_TOKEN_LIVER_MANAGER', 'THREADS_USER_ID_LIVER_MANAGER', 'THREADS_HANDLE_LIVER_MANAGER',
    'THREADS_ACCESS_TOKEN_BEAUTY_ACCOUNT', 'THREADS_USER_ID_BEAUTY_ACCOUNT', 'THREADS_HANDLE_BEAUTY_ACCOUNT',
    'BEAUTY_ACTIVATION_APPROVED', 'BUFFERED_POSTING_ENABLED', 'CLOUDINARY_CLOUD_NAME',
    'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET', 'GEMINI_API_KEY',
)
REQUIRED = {
    'Google service-account JSON': ('GCP_SA_JSON_BASE64', 'SA_JSON_BASE64'),
    'Spreadsheet ID': ('SPREADSHEET_ID', 'SNS_MASTER_SHEET_ID'),
    'Cloudinary cloud': ('CLOUDINARY_CLOUD_NAME',),
    'Cloudinary API key': ('CLOUDINARY_API_KEY',),
    'Cloudinary API secret': ('CLOUDINARY_API_SECRET',),
    'Gemini API key': ('GEMINI_API_KEY',),
}


def write_candidate_env(path: Path, runtime_root: Path, env: dict[str, str]) -> None:
    shared = runtime_root / 'shared'
    if (not shared.is_dir() or shared.is_symlink() or path.parent != shared or
            not path.name.startswith('.next-runtime-env.') or path.is_symlink() or path.exists()):
        raise ValueError('unsafe_candidate_env_destination')
    missing = [name for name, alternatives in REQUIRED.items() if not any(env.get(k) for k in alternatives)]
    if missing:
        raise ValueError('missing_required_runtime_configuration:' + ','.join(missing))
    if env.get('BUFFERED_POSTING_ENABLED', '').lower() not in {'true', 'false'}:
        raise ValueError('posting_mode_must_be_explicit_boolean')
    assignments = [(key, env.get(key, '')) for key in KEYS]
    assignments.append(('THREADS_TOKEN_STORE_DIR', str(shared / 'threads_tokens')))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            for key, value in assignments:
                handle.write(f'{key}={shlex.quote(value)}\n')
        os.chmod(path, 0o600)
        result = subprocess.run(['bash', '-n', str(path)], capture_output=True, check=False, timeout=10)
        if result.returncode:
            raise ValueError('invalid_serialized_environment')
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        write_candidate_env(args.out, args.runtime_root, dict(os.environ))
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print('[BLOCKED] candidate environment creation failed:', type(exc).__name__)
        return 78
    print('[OK] candidate environment created with mode 0600')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
