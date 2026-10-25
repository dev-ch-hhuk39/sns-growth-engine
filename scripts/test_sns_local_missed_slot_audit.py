#!/usr/bin/env python3
"""VPS missed-slot monitor cannot leak private draft fields or post."""
from __future__ import annotations
import json
import subprocess
import unittest
from unittest.mock import patch
import sns_local_missed_slot_audit as local

class MissedSlotAuditTests(unittest.TestCase):
    def test_scoped_no_write_dry_run(self):
        calls=[]
        def fake(cmd,**kw):
            calls.append((cmd,kw))
            return subprocess.CompletedProcess(cmd,0,json.dumps({'status':'PASS','dry_run':True,'results':[],'secret':'PRIVATE'}),'PRIVATE_TOKEN')
        with patch.object(local.subprocess,'run',side_effect=fake):
            status,summary=local.check_account('night_scout')
        self.assertEqual(status,0)
        self.assertNotIn('PRIVATE',summary)
        self.assertIn('SLOT_AUDIT_REDACTED',summary)
        cmd,kw=calls[0]
        self.assertIn('--dry-run',cmd)
        self.assertNotIn('--apply',cmd)
        self.assertEqual(kw['timeout'],180)
    def test_child_failure_not_laundered(self):
        body=json.dumps({'status':'PASS','dry_run':True,'results':[]})
        with patch.object(local.subprocess,'run',return_value=subprocess.CompletedProcess(['python'],2,body,'PRIVATE_ERROR')):
            code,summary=local.check_account('liver_manager')
        self.assertEqual(code,1)
        self.assertNotIn('PRIVATE_ERROR',summary)
    def test_invalid_document_fails_closed(self):
        for content in ('garbage',json.dumps({'status':'PASS','dry_run':False,'results':[]})):
            with self.subTest(content=content),patch.object(local.subprocess,'run',return_value=subprocess.CompletedProcess(['python'],0,content,'SECRET_PROVIDER')):
                code,summary=local.check_account('beauty_account')
            self.assertEqual(code,1)
            self.assertNotIn('SECRET_PROVIDER',summary)
    def test_all_three_independent(self):
        with patch.object(local,'check_account',side_effect=[(0,'A'),(1,'B'),(0,'C')]) as mocked:
            self.assertEqual(local.main(),1)
        self.assertEqual(mocked.call_count,3)
if __name__=='__main__':
    unittest.main()
