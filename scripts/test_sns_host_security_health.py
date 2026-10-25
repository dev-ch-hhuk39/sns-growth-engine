#!/usr/bin/env python3
"""Read-only local security monitoring always fails closed."""
from __future__ import annotations
import unittest
from unittest.mock import patch
import sns_host_security_health as monitor

class LocalMonitorTests(unittest.TestCase):
    def test_monitor_does_not_execute_mutating_commands(self):
        calls = []
        def fake(*args):
            calls.append(args)
            if args[:2] == ('readlink', '-f'):
                return 0, str(monitor.ROOT / 'releases' / ('a' * 40))
            if args[0] == 'df':
                return 0, 'Filesystem 1024-blocks Used Available Capacity Mounted\n/dev/vda1 100 76 24 76% /'
            if args[0] == 'systemctl':
                return 0, 'success' if args[1] == 'show' else 'enabled' if args[1] == 'is-enabled' else 'active'
            return 1, ''
        with patch.object(monitor, 'output', side_effect=fake), patch.object(
            monitor.Path, 'is_dir', return_value=True
        ), patch.object(monitor.Path, 'read_text', return_value='BUFFERED_POSTING_ENABLED=false\n'):
            outcome = monitor.audit()
        self.assertEqual(outcome['status'], 'PASS')
        self.assertTrue(outcome['no_post'])
        self.assertFalse(outcome['destructive_actions'])
        self.assertTrue(all(c[0] in ('systemctl','readlink','df') for c in calls))
        self.assertTrue(all(c[1] not in ('start','enable','delete','stop','restart') for c in calls))

    def test_status_unknown_blocks(self):
        with patch.object(monitor, 'output', return_value=(99,'')), patch.object(
            monitor.Path, 'read_text', side_effect=OSError('private path')
        ):
            outcome = monitor.audit()
        self.assertEqual(outcome['status'], 'BLOCKED')
        self.assertIn('posting_off', outcome['failed_checks'])
        self.assertIn('vps_disk_below_85pct', outcome['failed_checks'])

if __name__ == '__main__':
    unittest.main()
