#!/usr/bin/env python3
"""SNS-only local read-only operations and security checks; no GitHub dependency."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path('/opt/github-runners/sns-growth-engine/.buffered-runtime')
REQUIRED_UNITS = (
    'unattended-upgrades.service', 'apt-daily-upgrade.timer',
    'chadult-r2-offsite-backup.timer', 'chadult-r2-offsite-health.timer',
    'sns-growth-release-retention.timer',
)

def output(*args: str) -> tuple[int, str]:
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, check=False, timeout=12)
        return result.returncode, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 99, ''

def audit() -> dict:
    checks: dict[str, str] = {}
    for unit in REQUIRED_UNITS:
        rc, state = output('systemctl', 'is-enabled', unit)
        checks['unit_' + unit] = 'PASS' if rc == 0 and state == 'enabled' else 'BLOCKED'
    for service in ('ufw', 'fail2ban'):
        rc, state = output('systemctl', 'is-active', service)
        checks['service_' + service] = 'PASS' if rc == 0 and state == 'active' else 'BLOCKED'
    for service in ('chadult-r2-offsite-backup.service', 'chadult-r2-offsite-health.service'):
        rc, state = output('systemctl', 'show', service, '--property=Result', '--value')
        checks['last_result_' + service] = 'PASS' if rc == 0 and state == 'success' else 'BLOCKED'
    rc, current = output('readlink', '-f', str(ROOT / 'current'))
    checks['immutable_release'] = ('PASS' if rc == 0 and current.startswith(str(ROOT / 'releases') + '/')
                                   and len(Path(current).name) == 40 and Path(current).is_dir() else 'BLOCKED')
    env = ROOT / 'shared/runtime.env'
    try:
        values = [line.partition('=')[2].strip().lower() for line in env.read_text().splitlines()
                  if line.startswith('BUFFERED_POSTING_ENABLED=')]
        checks['posting_off'] = 'PASS' if values == ['false'] else 'BLOCKED'
    except OSError:
        checks['posting_off'] = 'BLOCKED'
    rc, data = output('df', '-P', '/')
    try:
        line = data.splitlines()[-1].split()
        used = int(line[4].rstrip('%'))
        checks['vps_disk_below_85pct'] = 'PASS' if rc == 0 and used < 85 else 'BLOCKED'
    except (IndexError, ValueError):
        checks['vps_disk_below_85pct'] = 'BLOCKED'
    failed = sorted(k for k, value in checks.items() if value != 'PASS')
    return {'status': 'PASS' if not failed else 'BLOCKED', 'failed_checks': failed,
            'checks': checks, 'no_post': True, 'destructive_actions': False}

def main() -> int:
    report = audit()
    print('SNS_LOCAL_SECURITY_HEALTH=' + json.dumps(report, sort_keys=True, separators=(',', ':')))
    return 0 if report['status'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
