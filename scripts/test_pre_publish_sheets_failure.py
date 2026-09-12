#!/usr/bin/env python3
"""Pre-publisher failures are terminal; ambiguous publication is never retried."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import process_threads_queue as worker
from content_slot_runs import release_unpublished_claim


class PrePublishTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(queue_id="test_only", account_id="night_scout", platform="threads", status="READY",
                        public_post_text="これからキャバを始める子は、時給だけで店を決めない方がいい。\n\n"
                        "客層や出勤ペース、担当へ相談しやすいかまで見ないと、"
                        "条件が良くても続けにくいことって結構ある。\n\n"
                        "僕なら、無理なく続けられる店か体入前に確認するんだよね。")

    def process(self, *, update=True, locked_rows=None, log_error=None, publish_error=None):
        locked = [{**self.row, "status": "PROCESSING"}] if locked_rows is None else locked_rows
        calls = []
        def publish(text, **kwargs):
            calls.append(kwargs['dry_run'])
            if not kwargs['dry_run'] and publish_error:
                raise publish_error
            return SimpleNamespace(success=kwargs['dry_run'], message="test transport", delivery_state="FAILED")
        with patch.dict(worker.os.environ, {"PUBLISH_ENABLED": "true", "ALLOW_REAL_THREADS_POST": "true"}), \
             patch.object(worker, 'records', side_effect=lambda _, tab: locked if tab == 'queue' else []), \
             patch.object(worker, 'update_row', side_effect=update if isinstance(update, Exception) else None, return_value=update), \
             patch.object(worker, 'log_event', side_effect=log_error), \
             patch.object(worker, 'ThreadsPublisher', return_value=SimpleNamespace(publish=publish)):
            result = worker.process_one(SimpleNamespace(), self.row, dry_run=False, confirm_real_post=True)
        return result, calls

    def test_missing_lock_and_429_never_publish(self):
        for update in (False, RuntimeError('429 private response')):
            result, calls = self.process(update=update)
            self.assertEqual(result['status'], 'PRE_PUBLISH_SHEETS_FAILED')
            self.assertIs(result['publish_attempted'], False)
            self.assertEqual(calls, [True])
            self.assertNotIn('private', str(result))

    def test_missing_duplicate_or_changed_queue_readback_blocks(self):
        good = {**self.row, 'status': 'PROCESSING'}
        for rows in ([], [good, good], [{**good, 'status': 'READY'}],
                     [{**good, 'account_id': 'liver_manager'}], [{**good, 'public_post_text': 'changed'}]):
            result, calls = self.process(locked_rows=rows)
            self.assertEqual(result['reason'], 'QUEUE_PROCESSING_LOCK_READBACK_FAILED')
            self.assertEqual(calls, [True])

    def test_log_failure_is_before_publish(self):
        result, calls = self.process(log_error=RuntimeError('429'))
        self.assertIs(result['publish_attempted'], False)
        self.assertEqual(calls, [True])

    def test_publisher_exception_is_not_classified_unpublished(self):
        with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
            self.process(publish_error=RuntimeError('ambiguous outcome'))

    def test_confirmed_api_failure_has_no_unpublished_claim_proof(self):
        result, calls = self.process()
        self.assertEqual(calls, [True, False])
        self.assertNotIn('publish_attempted', result)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.claim = dict(status='CLAIMED', slot_run_id='slot_test', publish_attempt_id='attempt_test')
        self.result = dict(status='PRE_PUBLISH_SHEETS_FAILED', publish_attempted=False, reason='QUEUE_PROCESSING_LOCK_FAILED', queue_id='q')
        self.row = {**self.claim, 'claim_status': 'CLAIMED', 'lease_expires_at': 'future'}

    def release(self, rows, *, readback_failure=False):
        state = [dict(row) for row in rows]
        ws = SimpleNamespace(get_all_records=lambda: [dict(row) for row in state])
        client = SimpleNamespace(_ensure_tab=lambda *_: ws, _call_with_rate_limit_retry=lambda _, f: f())
        def save(_, row):
            if not readback_failure:
                state[:] = [dict(row)]
        with patch('content_slot_runs.upsert_slot_run', side_effect=save) as write:
            result = release_unpublished_claim(client, self.claim, self.result)
        return result, write.call_count, state

    def test_release_and_readback(self):
        result, count, state = self.release([self.row])
        self.assertEqual(result['status'], 'RELEASED')
        self.assertEqual(count, 1)
        self.assertEqual(state[0]['status'], 'PRE_PUBLISH_FAILED')
        self.assertEqual(state[0]['lease_expires_at'], '')

    def test_no_release_of_changed_posted_or_duplicate_claim(self):
        for rows in ([], [self.row, self.row], [{**self.row, 'status': 'POSTED'}],
                     [{**self.row, 'publish_attempt_id': 'other'}], [{**self.row, 'result_id': 'posted'}]):
            result, count, _ = self.release(rows)
            self.assertEqual(result['status'], 'BLOCKED')
            self.assertEqual(count, 0)

    def test_readback_failure_is_not_success(self):
        result, _, _ = self.release([self.row], readback_failure=True)
        self.assertEqual(result['reason'], 'SLOT_RELEASE_READ_AFTER_WRITE_FAILED')

    def test_ambiguous_or_missing_proof_never_reads_or_writes(self):
        for result in ({'status': 'POSTED_SAVE_FAILED'}, {'status': 'PRE_PUBLISH_SHEETS_FAILED'},
                       {**self.result, 'publish_attempted': True}):
            self.assertEqual(release_unpublished_claim(None, self.claim, result)['reason'], 'NO_UNPUBLISHED_EXECUTION_PROOF')


if __name__ == '__main__':
    unittest.main()
