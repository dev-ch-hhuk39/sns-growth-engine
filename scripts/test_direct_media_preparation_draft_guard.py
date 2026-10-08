#!/usr/bin/env python3
import contextlib
import io
import unittest
from unittest.mock import patch

import run_direct_reference_media_pipeline as pipeline


class DirectMediaPreparationDraftGuardTests(unittest.TestCase):
    def test_prepare_only_is_allowed_while_publishing_is_disabled(self):
        output = io.StringIO()
        with patch('sys.argv', [
            'runner', '--account-id', 'liver_manager', '--slot-id', 'lm_1600_direct_media',
            '--apply', '--confirm-direct-media', '--prepare-only',
        ]), patch.object(pipeline, 'build_plan', return_value={
            'status': 'PLAN_ONLY', 'would_post': False,
        }), contextlib.redirect_stdout(output):
            code = pipeline.main()
        self.assertEqual(code, 0)
        self.assertNotIn('content_quality_v2_owner_review_required', output.getvalue())

    def test_publish_mode_remains_draft_only(self):
        output = io.StringIO()
        with patch('sys.argv', [
            'runner', '--account-id', 'liver_manager', '--slot-id', 'lm_1600_direct_media',
            '--apply', '--confirm-direct-media', '--post-ready',
        ]), contextlib.redirect_stdout(output):
            code = pipeline.main()
        self.assertEqual(code, 1)
        self.assertIn('"status": "DRAFT_ONLY"', output.getvalue())
        self.assertIn('content_quality_v2_owner_review_required', output.getvalue())


if __name__ == '__main__':
    unittest.main()
