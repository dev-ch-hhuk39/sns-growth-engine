#!/usr/bin/env python3
"""5B-6H static, review-gated inventory of existing Sheets mutation call sites.

This test FREEZES the baseline. It does not certify old callers as safe.
A new direct worksheet writer requires explicit security review and manifest
update; not a bypass through another untracked client in the same repository.
"""
from __future__ import annotations

import ast
import collections
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "PHASE5B6H_SHEETS_MUTATION_BASELINE.json"
MUTATORS = frozenset((
    "append_queue_item", "update_queue_item", "bulk_update_queue_items",
    "append_row", "append_rows", "update_row",
    "update_cell", "batch_update", "batch_clear",
    "insert_rows", "delete_rows", "resize", "clear",
    "delete_row", "insert_row", "add_rows", "add_cols",
))
SHEETS_RECEIVERS = ("ws", "worksheet", "sheet", "tab")


def _callee(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _callee(node.value) + "." + node.attr
    if isinstance(node, ast.Call):
        return _callee(node.func) + "()"
    return ""


def _kind(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        method = call.func.attr
        if method in MUTATORS:
            return method
        if method == "update":
            receiver = _callee(call.func.value).lower()
            if any(token in receiver for token in SHEETS_RECEIVERS):
                return "sheet_like.update"
    if (isinstance(call.func, ast.Name) and call.func.id == "getattr"
            and len(call.args) >= 2
            and isinstance(call.args[1], ast.Constant)
            and isinstance(call.args[1].value, str)
            and call.args[1].value in MUTATORS.union({"update"})):
        return "dynamic_getattr." + call.args[1].value
    return None


def collect_inventory() -> dict[str, dict[str, int]]:
    paths: dict[str, dict[str, int]] = {}
    for root in ("src", "scripts"):
        for source in sorted((ROOT / root).rglob("*.py")):
            if source.name.startswith("test_"):
                continue
            tree = ast.parse(source.read_text(encoding="utf-8"))
            calls = collections.Counter()
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    kind = _kind(node)
                    if kind:
                        calls[kind] += 1
            if calls:
                paths[source.relative_to(ROOT).as_posix()] = dict(sorted(calls.items()))
    return dict(sorted(paths.items()))


class LegacySheetsInventoryTests(unittest.TestCase):
    def test_every_known_mutation_route_still_matches_reviewed_baseline(self):
        snapshot = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(collect_inventory(), snapshot["routes"])

    def test_core_queue_callers_explicitly_present_in_baseline(self):
        snapshot = collect_inventory()
        for path in (
            "src/sheets_client.py", "src/queue_builder.py",
            "scripts/auto_approve_queue.py",
            "scripts/approve_queue.py",
            "scripts/publish_queue.py",
            "scripts/process_threads_queue.py",
            "scripts/recover_production_sheets_threads_first.py",
        ):
            self.assertIn(path, snapshot)
        self.assertGreater(
            sum(sum(v.values()) for v in snapshot.values()), 100,
        )

    def test_new_mutating_api_is_detected_without_using_the_network(self):
        tree = ast.parse(
            'client.append_queue_item({"status":"READY"})\n'
            'worksheet.update("A1", [[1]])\n'
            'getattr(ws, "update_cell")(1, 2, "READY")\n'
        )
        found = [
            _kind(node) for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        ]
        self.assertIn("append_queue_item", found)
        self.assertIn("sheet_like.update", found)
        self.assertIn("dynamic_getattr.update_cell", found)


if __name__ == "__main__":
    unittest.main()
