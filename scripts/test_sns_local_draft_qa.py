#!/usr/bin/env python3
"""Local QA is private, account-scoped and never confers queue approval."""
from __future__ import annotations

import copy
import io
import json
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sns_local_ollama_draft_bank as bank
from public_post_quality import generate_reader_facing_post


class LocalDraftQA(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.folder = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.account = "night_scout"
        self.text = generate_reader_facing_post(self.account, 1)["public_post_text"]
        self.path = self.folder / (self.account + "-pending-qa.json")
        self.document = {"schema": "sns_ollama_drafts_v1", "account_id": self.account,
            "status": "PENDING_HUMAN_QA", "canonical_bank_ready": False,
            "candidates": [{"draft_id": "local_one", "account_id": self.account,
                "post_type": "original_text", "source": "local_ollama_unverified",
                "draft_text": self.text, "workflow_status": "PENDING_HUMAN_QA", "canonical_bank_ready": False}]}
        self.write(self.document)

    def write(self, data):
        self.path.write_text(json.dumps(data, ensure_ascii=False))
        self.path.chmod(0o600)

    def test_valid_local_text_stays_pending_and_original_unchanged(self):
        before = self.path.read_bytes()
        report = bank.review_existing(self.account, self.folder)
        self.assertTrue(report["qa_completed"])
        self.assertEqual(report["draft_count"], 1)
        self.assertEqual(report["public_validation_pass"], 1)
        self.assertEqual(report["status"], "PENDING_HUMAN_QA")
        self.assertFalse(report["canonical_bank_ready"])
        self.assertEqual(report["ready_count"], 0)
        self.assertEqual(report["global_duplicate_scan"], "NOT_PERFORMED")
        self.assertEqual(report["runtime_publisher_check"], "NOT_PERFORMED")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertNotIn(self.text, json.dumps(report, ensure_ascii=False))
        self.assertNotIn("draft_text", json.dumps(report))
        self.assertNotIn("local_one", json.dumps(report))

    def test_qa_never_generates_or_writes_drafts(self):
        with patch.object(bank, "generate") as generate, patch.object(bank, "save") as save, \
                patch.object(bank.urllib.request, "build_opener") as network:
            report = bank.review_existing(self.account, self.folder)
        generate.assert_not_called()
        save.assert_not_called()
        network.assert_not_called()
        for field in ("model_calls", "paid_api_calls", "sheets_writes", "posts", "ready_count"):
            self.assertEqual(report[field], 0)

    def test_cli_qa_mode_does_not_take_generation_path(self):
        out = io.StringIO()
        with patch.object(bank, "STATE", self.folder), \
                patch.object(bank.sys, "argv", ["local-bank", "--account", self.account, "--qa-only"]), \
                patch.object(bank, "run") as generate_path, redirect_stdout(out):
            self.assertEqual(bank.main(), 0)
        generate_path.assert_not_called()
        data = json.loads(out.getvalue().split("=", 1)[1])
        self.assertEqual(data["mode"], "QA_ONLY")
        self.assertFalse(data["canonical_bank_ready"])
        self.assertNotIn(self.text, out.getvalue())

    def test_forged_approved_or_foreign_source_is_rejected(self):
        for update in ({"status": "READY"}, {"account_id": "liver_manager"},
                       {"canonical_bank_ready": True}, {"schema": "unknown"}):
            with self.subTest(update=update):
                doc = copy.deepcopy(self.document)
                doc.update(update)
                self.write(doc)
                with self.assertRaises(ValueError):
                    bank.review_existing(self.account, self.folder)

    def test_mixed_accounts_duplicate_ids_and_injected_approval_rejected(self):
        for update in ({"account_id": "liver_manager"}, {"workflow_status": "READY"},
                       {"canonical_bank_ready": True}, {"draft_text": None},
                       {"post_type": "direct_media"}, {"source": "verified"}):
            doc = copy.deepcopy(self.document)
            doc["candidates"][0].update(update)
            self.write(doc)
            with self.subTest(update=update), self.assertRaises(ValueError):
                bank.review_existing(self.account, self.folder)
        doc = copy.deepcopy(self.document)
        doc["candidates"].append(copy.deepcopy(doc["candidates"][0]))
        self.write(doc)
        with self.assertRaisesRegex(ValueError, "LOCAL_QA_ID_AMBIGUOUS"):
            bank.review_existing(self.account, self.folder)

    def test_unknown_claim_evidence_is_not_trusted(self):
        doc = copy.deepcopy(self.document)
        doc["candidates"][0]["draft_text"] = "僕なら月収100万円を保証します。" + self.text
        doc["candidates"][0]["supported_claims"] = [doc["candidates"][0]["draft_text"]]
        self.write(doc)
        report = bank.review_existing(self.account, self.folder)
        self.assertEqual(report["hard_gate_pass"], 0)
        self.assertIn("unsupported_high_risk_factual_claim", report["reason_counts"])
        self.assertEqual(report["ready_count"], 0)

    def test_symlinks_public_permissions_and_empty_sources_rejected(self):
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            bank.review_existing(self.account, self.folder)
        self.path.unlink()
        target = self.folder / "other.json"
        target.write_text(json.dumps(self.document))
        self.path.symlink_to(target)
        with self.assertRaises((OSError, ValueError)):
            bank.review_existing(self.account, self.folder)
        self.path.unlink()
        self.write({**self.document, "candidates": []})
        with self.assertRaises(ValueError):
            bank.review_existing(self.account, self.folder)

    def test_concurrent_source_change_cannot_receive_old_receipt(self):
        raw = self.path.read_bytes()
        with patch.object(bank, "_read_private_pending", side_effect=[raw, raw + b" "]):
            with self.assertRaisesRegex(ValueError, "SOURCE_CHANGED"):
                bank.review_existing(self.account, self.folder)

    def test_invalid_cli_source_does_not_leak_private_body(self):
        self.write({**self.document, "account_id": "PRIVATE_DO_NOT_PRINT"})
        out = io.StringIO()
        with patch.object(bank, "STATE", self.folder), \
                patch.object(bank.sys, "argv", ["local-bank", "--account", self.account, "--qa-only"]), redirect_stdout(out):
            self.assertEqual(bank.main(), 1)
        self.assertNotIn("PRIVATE_DO_NOT_PRINT", out.getvalue())
        self.assertNotIn(self.text, out.getvalue())


if __name__ == "__main__":
    unittest.main()
