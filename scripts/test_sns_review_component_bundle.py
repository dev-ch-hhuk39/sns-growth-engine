#!/usr/bin/env python3
"""Exercise packaged CLI mains with an in-memory Sheets boundary, never a provider."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import sns_review_component_bundle as bundle
from sns_local_publication_review_job import validated_result


class EmptySheet:
    def get_all_records(self):
        return []

    def row_values(self, number):
        assert number == 1
        return ['queue_id', 'account_id', 'review_decision', 'reviewer_note',
                'decision_applied_at', 'decision_result', 'review_status']

    def append_rows(self, *_args, **_kwargs):
        raise AssertionError('A no-op CLI must not write')

    batch_update = append_rows


class EmptyClient:
    dry_run = False

    def _ws(self, _name):
        return EmptySheet()


class ReviewBundleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.parent = Path(temp.name).resolve()
        self.destination = self.parent / 'component'
        self.contents = {name: (ROOT / name).read_bytes() for name in bundle.FILES}
        self.addCleanup(self.unlock)

    def unlock(self):
        if self.destination.is_dir():
            for path in (self.destination, self.destination/'config', self.destination/'scripts'):
                if path.is_dir():
                    path.chmod(0o700)

    def build(self):
        return bundle.build_from_contents(self.contents, self.destination, 'b'*40)

    def load(self, filename):
        spec = importlib.util.spec_from_file_location('packaged_'+filename[:-3], self.destination/'scripts'/filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.ROOT, self.destination)
        return module

    def test_bundle_contains_required_runtime_policy_and_readonly_sources(self):
        manifest = self.build()
        self.assertIn('config/autonomous_mode.json', manifest['files'])
        self.assertEqual((self.destination/'config/autonomous_mode.json').read_bytes(),
                         self.contents['config/autonomous_mode.json'])
        for name in manifest['files']:
            self.assertEqual((self.destination/name).stat().st_mode & 0o777, 0o444)
        self.assertEqual(self.destination.stat().st_mode & 0o777, 0o555)

    def test_missing_dependency_extra_secret_or_unpinned_revision_cannot_build(self):
        bad = dict(self.contents)
        bad.pop('config/autonomous_mode.json')
        for contents, revision in ((bad, 'b'*40), ({**self.contents,'.env':b'not allowed'}, 'b'*40),
                                   (self.contents, 'main')):
            with self.assertRaises(ValueError):
                bundle.build_from_contents(contents, self.destination, revision)
            self.assertFalse(self.destination.exists())

    def test_actual_packaged_cli_outputs_are_accepted_by_worker_noop_contract(self):
        self.build()
        for name, stage, confirm in (
            ('sync_publication_review.py', 'sync', '--confirm-review-sync'),
            ('apply_publication_review_decisions.py', 'decisions', '--confirm-review-decisions'),
        ):
            with self.subTest(name=name):
                module = self.load(name)
                output = io.StringIO()
                with patch.object(module, 'get_config', return_value={}), \
                        patch.object(module, 'make_client', return_value=EmptyClient()), \
                        patch('socket.create_connection', side_effect=AssertionError('No network')) as network, \
                        patch.object(sys, 'argv', [name, '--apply', confirm, '--use-sheets']), redirect_stdout(output):
                    self.assertEqual(module.main(), 0)
                network.assert_not_called()
                report = validated_result(stage, 0, output.getvalue())
                self.assertTrue(all(value == 0 for value in report.values()))

    def test_missing_packaged_policy_is_detected_before_any_client_construction(self):
        self.build()
        (self.destination/'config').chmod(0o700)
        (self.destination/'config/autonomous_mode.json').unlink()
        module = self.load('apply_publication_review_decisions.py')
        with patch.object(module, 'get_config', return_value={}), \
                patch.object(module, 'make_client') as client, \
                patch.object(sys, 'argv', ['decisions', '--apply', '--confirm-review-decisions', '--use-sheets']):
            with self.assertRaises(FileNotFoundError):
                module.main()
        client.assert_not_called()


if __name__ == '__main__':
    unittest.main()
