#!/usr/bin/env python3
"""Scope check for safe interrupted SNS installation stage retention."""
import os
import tempfile
import time
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.cleanup_owned_sns_deploy_stages import candidates


class StaleStageTests(unittest.TestCase):
    def test_only_old_marked_unprotected_sns_stages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / '.buffered-runtime'
            releases = root / 'releases'
            releases.mkdir(parents=True)
            current = releases / ('a'*40)
            previous = releases / ('b'*40)
            current.mkdir(); previous.mkdir()
            (root / 'current').symlink_to(current)
            (root / 'previous').symlink_to(previous)
            sha = 'c'*40
            old = releases / ('.stage-' + sha + '.ABC123')
            old.mkdir()
            (old / '.sns-deploy-stage-owned').write_text(sha + '\n')
            another = releases / ('.stage-' + ('d'*40) + '.ABC123')
            another.mkdir()
            (another / '.sns-deploy-stage-owned').write_text('not-this-release\n')
            young = releases / ('.stage-' + ('e'*40) + '.ABC123')
            young.mkdir()
            (young / '.sns-deploy-stage-owned').write_text('e'*40 + '\n')
            ts = time.time() - 9 * 86400
            os.utime(old, (ts, ts)); os.utime(another, (ts, ts))
            self.assertEqual(candidates(root), [old])
            (root / 'pending').symlink_to(old)
            self.assertEqual(candidates(root), [])
            self.assertTrue(old.exists())


if __name__ == '__main__':
    unittest.main()
