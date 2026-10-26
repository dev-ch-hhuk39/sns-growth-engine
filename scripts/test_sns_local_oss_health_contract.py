#!/usr/bin/env python3
"""No-network contract for the offline, Mac-owned research stack checks."""
from pathlib import Path
import plistlib
import unittest

ROOT=Path(__file__).resolve().parents[1]


class MacOSSHealthTests(unittest.TestCase):
    def test_pinned_and_nonpublishing(self):
        sh=(ROOT/'scripts/run_local_oss_library_health.sh').read_text()
        self.assertIn('249c7a4c040558a903d6838dee31012980d4946d',sh)
        self.assertIn('rev-parse HEAD',sh)
        self.assertIn('--preflight',sh)
        self.assertIn('PUBLISH_ENABLED=false',sh)
        self.assertIn('ALLOW_REAL_THREADS_POST=false',sh)
        self.assertNotIn('gh workflow',sh)
        self.assertNotIn(' --apply ',sh)
        self.assertNotIn('curl -X POST',sh)
        self.assertIn('PREFLIGHT_PY=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3',sh)
    def test_weekly_launchd_scope(self):
        with (ROOT/'ops/launchd/com.chadult.sns.oss-library-health.plist').open('rb') as f:
            p=plistlib.load(f)
        self.assertEqual(p['Label'],'com.chadult.sns.oss-library-health')
        self.assertEqual(p['StartCalendarInterval'],{'Weekday':1,'Hour':3,'Minute':17})
        self.assertFalse(p['RunAtLoad'])
        self.assertEqual(p['ProgramArguments'][0],'/bin/bash')
        self.assertTrue(p['ProgramArguments'][1].endswith('run_local_oss_library_health.sh'))


if __name__=='__main__':
    unittest.main()
