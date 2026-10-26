#!/usr/bin/env python3
"""Verify the owner's GitHub App ID on the VPS; never refresh or expose it.

GitHub can inject the configured ID into this manual job without revealing
Secrets through its API. Only a passing unchanged renewal preflight permits
creating the independent, private App-ID-only environment file.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

RUNTIME = Path('/opt/github-runners/sns-growth-engine/.buffered-runtime')
BUNDLE = Path('/usr/local/libexec/chadult-sns-token-renewal/cc578f8a5cef169679583aca05652a95398a8fbc')
# Installed-source SHA-256 digests, in the same order as the code filenames.
SOURCE_SHA256 = (
    '0d6416cb9d2f46868e0050964d4873a699857e4f76e8e8eb27f3821de837ff35',
    '989b227fef1b7da1d45a3dc66ae13169374325975c9eb60a8e7f624ef5818160',
)
CODE_FILENAMES = ('sns_local_threads_token_renewal.py', 'sns_local_threads_expiry_watch.py')
PIN_NAME = 'threads_app_ids.env'
PIN_KEY = 'THREADS_APP_ID_LIVER_MANAGER'
CONFIRM = 'VERIFY_LIVER_APP_ID'


class PinBlocked(ValueError):
    """Only fixed reason codes are emitted."""


def private_metadata(path: Path, *, directory: bool = False) -> os.stat_result:
    meta = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (not kind(meta.st_mode) or meta.st_uid != os.getuid()
            or meta.st_mode & (0o022 if directory else 0o077)
            or (not directory and meta.st_nlink != 1)):
        raise PinBlocked('PRIVATE_HOST_PATH_UNVERIFIED')
    return meta


def validated_preflight(code: int, output: str) -> dict:
    if len(output.encode()) > 100_000:
        raise PinBlocked('APP_PIN_PREFLIGHT_BLOCKED')
    lines = [s.split('=', 1)[1] for s in output.splitlines()
             if s.startswith('SNS_LOCAL_THREADS_TOKENS=')]
    try:
        data = json.loads(lines[0]) if len(lines) == 1 else {}
        if (code != 0 or data.get('status') != 'DRY_RUN' or data.get('posts') != 0
                or data.get('github_secrets_changed') is not False
                or set(data.get('accounts', {})) != {'liver_manager'}):
            raise ValueError()
        account = data['accounts']['liver_manager']
        if (not isinstance(account, dict) or account.get('status') != 'DRY_RUN'
                or account.get('posts') != 0
                or account.get('accounts') not in ({'liver_manager': 'DUE'}, {'liver_manager': 'CURRENT'})
                or type(account.get('refresh_due')) is not int
                or account['refresh_due'] not in (0, 1)):
            raise ValueError()
    except (ValueError, TypeError, IndexError):
        raise PinBlocked('APP_PIN_PREFLIGHT_UNVERIFIED') from None
    return account


def lifecycle_diagnostic(runtime: Path, candidate: str) -> str:
    """One bounded read using the same verified helper; return fixed codes only."""
    current = (runtime / 'current').resolve(strict=True)
    program = '''import importlib.util,json,sys
from pathlib import Path
root=Path(sys.argv[1]);bundle=Path(sys.argv[2])
sys.path[:0]=[str(root/'src'),str(root/'scripts')]
from publishers.threads_credentials import resolve_credentials
spec=importlib.util.spec_from_file_location('approved_watch',bundle/'sns_local_threads_expiry_watch.py')
watch=importlib.util.module_from_spec(spec);spec.loader.exec_module(watch)
codes={'META_APP_ID_MISMATCH','META_ISSUED_AT_UNVERIFIED','META_ACCOUNT_ID_MISMATCH',
       'META_BASIC_SCOPE_MISSING','META_EXPIRY_INVALID','META_TOKEN_EXPIRED',
       'CREDENTIALS_NOT_CONFIGURED','TOKEN_SIZE_INVALID'}
try:
 watch.check_one('liver_manager',resolve_credentials('liver_manager'),include_lifecycle=True)
 reason='LIFECYCLE_VERIFIED'
except Exception as exc:
 reason=str(exc) if str(exc) in codes else 'LIFECYCLE_UNVERIFIED'
print(json.dumps({'reason':reason,'token_refreshes':0}))
'''
    command = ('set -euo pipefail; set +x; set -a; . "$1"; set +a; '
               'export THREADS_APP_ID_LIVER_MANAGER="$CANDIDATE_LIVER_THREADS_APP_ID"; '
               'exec "$2" -B -c "$3" "$4" "$5"')
    result = subprocess.run(
        ['bash', '--noprofile', '--norc', '-c', command, 'app-pin-diagnostic',
         str(runtime / 'shared/runtime.env'), str(current / '.venv/bin/python'),
         program, str(current), str(BUNDLE)],
        env={**os.environ, 'CANDIDATE_LIVER_THREADS_APP_ID': candidate},
        cwd=current, capture_output=True, text=True, timeout=60, check=False,
    )
    allowed = {'META_APP_ID_MISMATCH', 'META_ISSUED_AT_UNVERIFIED', 'META_ACCOUNT_ID_MISMATCH',
               'META_BASIC_SCOPE_MISSING', 'META_EXPIRY_INVALID', 'META_TOKEN_EXPIRED',
               'CREDENTIALS_NOT_CONFIGURED', 'TOKEN_SIZE_INVALID', 'LIFECYCLE_VERIFIED'}
    try:
        data = json.loads(result.stdout) if result.returncode == 0 else {}
        return data['reason'] if data.get('reason') in allowed else 'LIFECYCLE_UNVERIFIED'
    except (ValueError, TypeError, KeyError):
        return 'LIFECYCLE_UNVERIFIED'


def preflight(runtime: Path, candidate: str) -> dict:
    current = (runtime / 'current').resolve(strict=True)
    if current.parent != runtime / 'releases':
        raise PinBlocked('CANONICAL_RELEASE_UNVERIFIED')
    for name, expected in zip(CODE_FILENAMES, SOURCE_SHA256, strict=True):
        path = BUNDLE / name
        meta = path.lstat()
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0 or meta.st_mode & 0o222
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
            raise PinBlocked('APP_PIN_HELPER_SOURCE_UNVERIFIED')
    # The established host environment is protected; shell tracing is never
    # enabled. The supplied App ID overrides only Liver after loading it.
    command = ('set -euo pipefail; set +x; set -a; . "$1"; set +a; '
               'export THREADS_APP_ID_LIVER_MANAGER="$CANDIDATE_LIVER_THREADS_APP_ID"; '
               'exec "$2" -B "$3" --account-id liver_manager')
    result = subprocess.run(
        ['bash', '--noprofile', '--norc', '-c', command, 'app-pin-preflight',
         str(runtime / 'shared/runtime.env'), str(current / '.venv/bin/python'),
         str(BUNDLE / 'sns_local_threads_token_renewal.py')],
        env={**os.environ, 'CANDIDATE_LIVER_THREADS_APP_ID': candidate},
        cwd=current, capture_output=True, text=True, timeout=180, check=False,
    )
    if (runtime / 'current').resolve(strict=True) != current:
        raise PinBlocked('CANONICAL_RELEASE_CHANGED')
    if result.returncode != 0:
        reason = lifecycle_diagnostic(runtime, candidate)
        raise PinBlocked('APP_PIN_PREFLIGHT_BLOCKED_' + reason)
    return validated_preflight(result.returncode, result.stdout)


def run(candidate: str, *, apply_pin: bool, runtime: Path = RUNTIME) -> dict:
    if not re.fullmatch(r'[0-9]{5,30}', candidate):
        raise PinBlocked('GITHUB_APP_ID_MISSING_OR_INVALID')
    shared = runtime / 'shared'
    private_metadata(shared, directory=True)
    private_metadata(shared / 'threads_tokens', directory=True)
    def env_fingerprint():
        meta = private_metadata(shared / 'runtime.env')
        return (meta.st_dev, meta.st_ino, meta.st_size, meta.st_mtime_ns, meta.st_mode, meta.st_uid)
    env_meta = env_fingerprint()
    pin = shared / PIN_NAME
    payload = (PIN_KEY + '=' + candidate + '\n').encode('ascii')
    if pin.exists() or pin.is_symlink():
        private_metadata(pin)
        if pin.read_bytes() != payload:
            raise PinBlocked('EXISTING_APP_PIN_REQUIRES_RECONCILIATION')
    lock = shared / 'threads_tokens/.threads-refresh.lock'
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        private_metadata(lock)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verified = preflight(runtime, candidate)
        if env_fingerprint() != env_meta:
            raise PinBlocked('HOST_ENVIRONMENT_CHANGED')
        wrote = False
        if apply_pin:
            try:
                outfd = os.open(pin, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                private_metadata(pin)
                if pin.read_bytes() != payload:
                    raise PinBlocked('EXISTING_APP_PIN_REQUIRES_RECONCILIATION') from None
            else:
                with os.fdopen(outfd, 'wb') as out:
                    out.write(payload)
                    out.flush()
                    os.fsync(out.fileno())
                dirfd = os.open(shared, os.O_RDONLY)
                try:
                    os.fsync(dirfd)
                finally:
                    os.close(dirfd)
                wrote = True
            private_metadata(pin)
            if pin.read_bytes() != payload:
                raise PinBlocked('APP_PIN_READBACK_UNVERIFIED')
        return {'status': 'VERIFIED_PIN' if apply_pin else 'VERIFIED_PREVIEW',
                'account': 'liver_manager', 'refresh_due': verified['refresh_due'],
                'app_id_matched': True, 'configuration_writes': int(wrote),
                'token_refreshes': 0, 'posts': 0, 'sheets_writes': 0,
                'github_secrets_changed': False}
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm', required=True)
    parser.add_argument('--apply-pin', action='store_true')
    args = parser.parse_args()
    try:
        if args.confirm != CONFIRM:
            raise PinBlocked('APP_PIN_CONFIRMATION_REQUIRED')
        data = run(os.environ.get('CANDIDATE_LIVER_THREADS_APP_ID', ''), apply_pin=args.apply_pin)
    except Exception as exc:
        data = {'status': 'BLOCKED', 'reason': str(exc) if isinstance(exc, PinBlocked)
                else 'APP_PIN_RUNTIME_UNVERIFIED', 'token_refreshes': 0, 'posts': 0, 'sheets_writes': 0}
    print('SNS_GITHUB_APP_PIN=' + json.dumps(data, sort_keys=True))
    return 0 if data['status'].startswith('VERIFIED_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
