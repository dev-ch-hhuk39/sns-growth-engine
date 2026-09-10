#!/usr/bin/env python3
"""The complete production verifier must retain checks with bounded reads."""
import copy
import unittest
from unittest.mock import patch

import recover_production_sheets_threads_first as core
from test_recover_verify_ready_checks import _FakeClient, _base_tabs


class SnapshotTests(unittest.TestCase):
    def test_one_batch_reads_all_verification_tabs(self):
        client = _FakeClient(_base_tabs())
        with patch.object(client, "values_batch_get", wraps=client.values_batch_get) as batch, \
                patch.object(client, "_call_with_rate_limit_retry", wraps=client._call_with_rate_limit_retry) as retry:
            snapshot = core._verification_records(client)
        self.assertEqual(set(snapshot), set(core.VERIFICATION_TABS))
        self.assertEqual(len(snapshot), 18)
        batch.assert_called_once()
        retry.assert_called_once()
        self.assertEqual(len(batch.call_args.args[0]), 18)

    def test_fresh_after_changes_and_no_client_cache(self):
        tabs = _base_tabs()
        client = _FakeClient(tabs)
        self.assertEqual(core._verification_records(client)["queue"], [])
        tabs["queue"] = [{"queue_id": "q_new", "status": "READY"}]
        self.assertEqual(core._verification_records(client)["queue"][0]["queue_id"], "q_new")

    def test_missing_range_and_ambiguous_headers_fail_closed(self):
        client = _FakeClient(_base_tabs())
        with patch.object(client, "values_batch_get", return_value={"valueRanges": []}):
            with self.assertRaisesRegex(RuntimeError, "range_count_mismatch"):
                core._verification_records(client)
        invalid = {"valueRanges": [{"values": [["id", "id"], ["a", "b"]]}] * 18}
        with patch.object(client, "values_batch_get", return_value=invalid):
            with self.assertRaisesRegex(RuntimeError, "duplicate_nonempty_headers"):
                core._verification_records(client)

    def test_transport_failure_never_becomes_empty_pass(self):
        client = _FakeClient(_base_tabs())
        with patch.object(client, "values_batch_get", side_effect=RuntimeError("quota_exhausted")):
            with self.assertRaisesRegex(RuntimeError, "quota_exhausted"):
                core.verify_state(client)

    def test_same_verification_as_individual_records(self):
        tabs = _base_tabs()
        tabs["queue"] = [{"queue_id": "bad", "platform": "x", "account_id": "night_scout", "status": "READY"}]
        client = _FakeClient(tabs)
        actual = core.verify_state(client)
        records = {name: copy.deepcopy(tabs.get(name, [])) for name in core.VERIFICATION_TABS}
        with patch.object(core, "_verification_records", return_value=records):
            expected = core.verify_state(client)
        self.assertEqual(actual, expected)
        self.assertFalse(actual["checks"]["no_ready_for_x_or_beauty"])


if __name__ == "__main__":
    unittest.main()
