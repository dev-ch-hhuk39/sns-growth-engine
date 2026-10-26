#!/usr/bin/env python3
"""Local READY audit never posts, writes or emits raw provider errors."""
import json
import subprocess
import unittest
from unittest.mock import patch
import sns_local_ready_audit as local


class ReadyReadOnlyAuditTests(unittest.TestCase):
    def test_no_writes_no_posts_and_private_stdout_not_emitted(self):
        private = {'status':'PASS', 'would_post':False, 'results':[], 'private_draft':'DO_NOT_PRINT'}
        captured=[]
        def fake_run(args, **kwargs):
            captured.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, json.dumps(private), 'PRIVATE_TOKEN')
        with patch.object(local.subprocess,'run',side_effect=fake_run), patch.object(
            local,'render_report',return_value='redacted status only'):
            rc, summary=local.run_one('night_scout')
        self.assertEqual(rc,0)
        self.assertEqual(summary,'redacted status only')
        self.assertNotIn('DO_NOT_PRINT', summary)
        self.assertNotIn('PRIVATE_TOKEN', summary)
        command,kwargs=captured[0]
        self.assertIn('--dry-run',command)
        self.assertIn('--use-sheets',command)
        self.assertIn('--horizon-hours',command)
        self.assertNotIn('--apply',command)
        self.assertEqual(kwargs['timeout'],240)

    def test_failure_produces_only_fixed_reason(self):
        args=['python']
        for out in ('not json', json.dumps({'status':'PASS','would_post':True})):
            with self.subTest(out=out), patch.object(local.subprocess,'run',return_value=
                subprocess.CompletedProcess(args,1,out,'SECRET_PROVIDER_MESSAGE')):
                rc,summary=local.run_one('beauty_account')
            self.assertEqual(rc,1)
            self.assertIn('REPORT_UNVERIFIED',summary)
            self.assertNotIn('SECRET_PROVIDER_MESSAGE',summary)

    def test_failure_one_account_does_not_suppress_other_accounts(self):
        with patch.object(local,'run_one',side_effect=[(0,'A'),(1,'B'),(0,'C')]) as checked:
            self.assertEqual(local.main(),1)
        self.assertEqual(checked.call_count,3)

if __name__=='__main__':
    unittest.main()
