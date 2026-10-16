#!/usr/bin/env python3
"""Publisher persistence must not coerce IDs into spreadsheet numbers."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import process_threads_queue as worker


class Worksheet:
    def __init__(self):
        self.appended = None
        self.updated = None
        self.row = {"result_id": "result", "external_post_id": ""}

    def append_row(self, values, *, value_input_option):
        self.appended = (values, value_input_option)

    def findall(self, value, *, in_column):
        return ([SimpleNamespace(row=2, value="result")]
                if in_column == 1 and value == "result" else [])

    def row_values(self, number):
        assert number == 2
        return [self.row["result_id"], self.row["external_post_id"]]

    def batch_update(self, ranges, *, value_input_option):
        self.updated = (ranges, value_input_option)
        for item in ranges:
            assert item["range"] == "B2"
            self.row["external_post_id"] = item["values"][0][0]


class PersistenceTests(unittest.TestCase):
    def test_append_retains_full_id_and_literal_text(self):
        ws = Worksheet()
        post_id = "18066501234567891"
        with patch.object(worker, "get_ws", return_value=ws), \
             patch.object(worker, "_get_headers", return_value=["external_post_id", "posted_text"]):
            worker.append_row(object(), "posted_results",
                              {"external_post_id": post_id, "posted_text": "=literal public text"})
        self.assertEqual(ws.appended, ([post_id, "=literal public text"], "RAW"))

    def test_update_retains_full_id(self):
        ws = Worksheet()
        with patch.object(worker, "get_ws", return_value=ws), \
             patch.object(worker, "_get_headers", return_value=["result_id", "external_post_id"]):
            self.assertTrue(worker.update_row(object(), "posted_results", "result_id", "result",
                                              {"external_post_id": "18066501234567891"}))
        self.assertEqual(ws.updated, ([{"range": "B2", "values": [["18066501234567891"]]}], "RAW"))


if __name__ == "__main__":
    unittest.main()
