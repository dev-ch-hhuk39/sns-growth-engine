#!/usr/bin/env python3
"""Write a 0600 candidate-only SNS runtime environment; never overwrite live."""
from __future__ import annotations
import argparse
import os
import shlex
import stat
import re
import subprocess
from pathlib import Path

KEYS = (
    'GCP_SA_JSON_BASE64', 'SA_JSON_BASE64', 'SPREADSHEET_ID', 'SNS_MASTER_SHEET_ID',
    'THREADS_ACCESS_TOKEN_NIGHT_SCOUT', 'THREADS_USER_ID_NIGHT_SCOUT', 'THREADS_HANDLE_NIGHT_SCOUT',
    'THREADS_ACCESS_TOKEN_LIVER_MANAGER', 'THREADS_USER_ID_LIVER_MANAGER', 'THREADS_HANDLE_LIVER_MANAGER',
    'THREADS_ACCESS_TOKEN_BEAUTY_ACCOUNT', 'THREADS_USER_ID_BEAUTY_ACCOUNT', 'THREADS_HANDLE_BEAUTY_ACCOUNT',
    'THREADS_APP_ID_NIGHT_SCOUT', 'THREADS_APP_ID_LIVER_MANAGER', 'THREADS_APP_ID_BEAUTY_ACCOUNT',
    'BEAUTY_ACTIVATION_APPROVED', 'BUFFERED_POSTING_ENABLED', 'CLOUDINARY_CLOUD_NAME',
    'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET', 'GEMINI_API_KEY',
)
# P0 HMAC material belongs ONLY to the already protected single host.
# Never copy it from CI environment variables or Actions secrets.
HOST_ONLY_P0 = (
    'SNS_P0_ONCE_GATE_ENABLED',
    'SNS_P0_ONCE_DB_PATH',
    'SNS_P0_ONCE_HMAC_KEY_HEX',
)
MODE_ONLY_P0 = 'SNS_P0_AUTONOMY_MODE'
# Existing independent aftercare consents belong to the protected host too.
# A deploy caller cannot grant them, and missing consents stay disabled.
HOST_ONLY_AFTERCARE = (
    'AFTERCARE_METRICS_WRITE_APPROVED',
    'AFTERCARE_ACTIONS_DISABLED_ATTESTED',
    'AFTERCARE_STRATEGY_WRITE_APPROVED',
    'AFTERCARE_READY_BANK_REUSE_APPROVED',
)
HOST_ONLY_PREPARATION = (
    'AUTO_READY_WRITE_APPROVED',
    'AUTO_READY_ACTIONS_DISABLED_ATTESTED',
    'AUTO_READY_OFFLINE_GENERATION_APPROVED',
    'ACQUISITION_WRITE_APPROVED',
    'ACQUISITION_ACTIONS_DISABLED_ATTESTED',
)
HOST_ONLY_ACQUISITION_SCOPE = (
    'ACQUISITION_APPROVED_ACCOUNT',
    'ACQUISITION_APPROVED_SCOPE',
    'ACQUISITION_APPROVED_PLATFORM',
    'ACQUISITION_APPROVED_RELEASE',
)


def inherited_p0_env(source: Path, shared: Path) -> dict[str, str]:
    """Read whitelisted controls from the already protected host source."""
    if source.parent != shared or source.is_symlink() or not source.is_file():
        raise ValueError('untrusted_host_env_source')
    st = source.stat()
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
            or stat.S_IMODE(st.st_mode) != 0o600):
        raise ValueError('untrusted_host_env_permissions')
    result: dict[str, str] = {}
    seen = set()
    for raw in source.read_text(encoding='utf-8').splitlines():
        if not raw.strip():
            continue
        parts = shlex.split(raw)
        if len(parts) != 1 or '=' not in parts[0]:
            raise ValueError('host_env_serialization_unverified')
        key, value = parts[0].split('=', 1)
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or key in seen:
            raise ValueError('host_env_key_invalid_or_duplicate')
        seen.add(key)
        if (key in HOST_ONLY_P0 or key == MODE_ONLY_P0 or key in HOST_ONLY_AFTERCARE
                or key in HOST_ONLY_PREPARATION or key in HOST_ONLY_ACQUISITION_SCOPE):
            result[key] = value
    return result


REQUIRED = {
    'Google service-account JSON': ('GCP_SA_JSON_BASE64', 'SA_JSON_BASE64'),
    'Spreadsheet ID': ('SPREADSHEET_ID', 'SNS_MASTER_SHEET_ID'),
    'Cloudinary cloud': ('CLOUDINARY_CLOUD_NAME',),
    'Cloudinary API key': ('CLOUDINARY_API_KEY',),
    'Cloudinary API secret': ('CLOUDINARY_API_SECRET',),
    'Gemini API key': ('GEMINI_API_KEY',),
}


def write_candidate_env(path: Path, runtime_root: Path, env: dict[str, str],
                        *, inherit_local_p0: Path | None = None) -> None:
    shared = runtime_root / 'shared'
    if (not shared.is_dir() or shared.is_symlink() or path.parent != shared or
            not path.name.startswith('.next-runtime-env.') or path.is_symlink() or path.exists()):
        raise ValueError('unsafe_candidate_env_destination')
    missing = [name for name, alternatives in REQUIRED.items() if not any(env.get(k) for k in alternatives)]
    if missing:
        raise ValueError('missing_required_runtime_configuration:' + ','.join(missing))
    if env.get('BUFFERED_POSTING_ENABLED', '').lower() not in {'true', 'false'}:
        raise ValueError('posting_mode_must_be_explicit_boolean')
    for key in ('THREADS_APP_ID_NIGHT_SCOUT', 'THREADS_APP_ID_LIVER_MANAGER', 'THREADS_APP_ID_BEAUTY_ACCOUNT'):
        if env.get(key) and not re.fullmatch(r'[0-9]{5,30}', env[key]):
            raise ValueError('threads_app_id_must_be_numeric')
    inherited = (
        inherited_p0_env(inherit_local_p0, shared)
        if inherit_local_p0 is not None else {}
    )
    gate = inherited.get('SNS_P0_ONCE_GATE_ENABLED', 'false')
    if gate not in {'false', 'true'}:
        raise ValueError('host_p0_gate_boolean_invalid')
    autonomy_mode = inherited.get('SNS_P0_AUTONOMY_MODE', 'canary')
    if autonomy_mode not in {'canary', 'continuous'}:
        raise ValueError('host_p0_autonomy_mode_invalid')
    aftercare = {key: inherited.get(key, 'false') for key in HOST_ONLY_AFTERCARE}
    if any(value not in {'true', 'false'} for value in aftercare.values()):
        raise ValueError('host_aftercare_approval_boolean_invalid')
    preparation = {key: inherited.get(key, 'false') for key in HOST_ONLY_PREPARATION}
    if any(value not in {'true', 'false'} for value in preparation.values()):
        raise ValueError('host_preparation_approval_boolean_invalid')
    acquisition = {key: inherited.get(key, '') for key in HOST_ONLY_ACQUISITION_SCOPE}
    if (acquisition['ACQUISITION_APPROVED_ACCOUNT'] not in {'', 'night_scout', 'liver_manager', 'beauty_account'}
            or acquisition['ACQUISITION_APPROVED_SCOPE'] not in {'', 'approved', 'reference-only'}
            or acquisition['ACQUISITION_APPROVED_PLATFORM'] not in {'', 'x', 'youtube'}
            or (acquisition['ACQUISITION_APPROVED_RELEASE']
                and not re.fullmatch(r'[0-9a-f]{40}', acquisition['ACQUISITION_APPROVED_RELEASE']))):
        raise ValueError('host_acquisition_scope_invalid')
    if env.get('BUFFERED_POSTING_ENABLED') == 'true':
        if (gate != 'true' or
                not Path(inherited.get('SNS_P0_ONCE_DB_PATH') or '').is_absolute()
                or not re.fullmatch(r'[0-9a-fA-F]{64,}', inherited.get(
                    'SNS_P0_ONCE_HMAC_KEY_HEX', ''))
                or len(inherited['SNS_P0_ONCE_HMAC_KEY_HEX']) % 2):
            raise ValueError('host_p0_authority_not_configured')
    assignments = [(key, env.get(key, '')) for key in KEYS]
    assignments.extend((key, inherited.get(key, 'false' if key ==
                        'SNS_P0_ONCE_GATE_ENABLED' else '')) for key in HOST_ONLY_P0)
    assignments.append((MODE_ONLY_P0, autonomy_mode))
    assignments.extend(aftercare.items())
    assignments.extend(preparation.items())
    assignments.extend(acquisition.items())
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
    parser.add_argument('--inherit-local-p0', type=Path)
    args = parser.parse_args()
    try:
        write_candidate_env(
            args.out, args.runtime_root, dict(os.environ),
            inherit_local_p0=args.inherit_local_p0,
        )
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print('[BLOCKED] candidate environment creation failed:', type(exc).__name__)
        return 78
    print('[OK] candidate environment created with mode 0600')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
