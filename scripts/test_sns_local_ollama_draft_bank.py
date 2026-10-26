#!/usr/bin/env python3
"""No-network verification that local drafts never become publish-ready."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest

import sns_local_ollama_draft_bank as bank


class OfflineDraftTests(unittest.TestCase):
    def test_qualified_mode_uses_real_gates_and_keeps_original_file(self):
        root = Path(__file__).resolve().parents[1]
        candidates = json.loads((root/'config/offline_original_posts.json').read_text())['night_scout']
        text = next(t for t in candidates if bank.local_quality('night_scout', t, [])[0])
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            original = parent/'night_scout-pending-qa.json'
            original.write_text('preserve existing raw ideas')
            before = original.read_bytes()
            with patch.object(bank, 'generate', return_value=[{'hook': '', 'body': text}]):
                result = bank.run('night_scout', 1, parent/'quality-reserve', require_quality=True)
            self.assertEqual(result['draft_count'], 1)
            self.assertEqual(result['local_qa']['whole_batch_checks_pass'], 1)
            self.assertEqual(result['ready_count'], 0)
            self.assertEqual(result['status'], 'PENDING_HUMAN_QA')
            self.assertEqual(original.read_bytes(), before)

    def test_qualified_mode_rejects_unsafe_claims_without_lowering_gates(self):
        text = '僕なら月収100万円を保証します。' * 5
        with tempfile.TemporaryDirectory() as temporary, patch.object(bank, 'generate', return_value=[{'hook':'','body':text}]):
            result = bank.run('night_scout', 1, Path(temporary), require_quality=True)
        self.assertEqual(result['draft_count'], 0)
        self.assertEqual(result['model_calls'], 25)
        self.assertEqual(result['ready_count'], 0)

    def test_audit_and_generation_flags_cannot_be_combined(self):
        import io
        from contextlib import redirect_stdout
        with patch.object(bank.sys, 'argv', ['bank','--account','night_scout','--qa-only','--qualified-only']), \
                patch.object(bank, 'run') as generate, patch.object(bank, 'review_existing') as review, redirect_stdout(io.StringIO()):
            self.assertEqual(bank.main(), 1)
        generate.assert_not_called()
        review.assert_not_called()

    def test_dedupe_and_forbidden_expression(self):
        text = "次の配信を振り返るなら何を見る？\n視聴人数だけでなく、リスナーと会話できた時間帯をメモすると、次の話題の準備が具体的になります。"
        self.assertEqual(bank.validate(text, [], []), "PASS")
        self.assertEqual(bank.validate(text, [text], []), "DUPLICATE")
        self.assertEqual(bank.validate(text, [], ["視聴人数"]), "FORBIDDEN")
        self.assertEqual(bank.validate(text + " https://example.com", [], []), "LINK")
        self.assertEqual(bank.validate(text.replace("視聴人数", "必ず儲かる"), [], []), "CLAIM")

    def test_private_qa_preview_only(self):
        text = "話題が尽きそうなときどうする？\n配信前に話せるテーマを3つ書き出しておくと、一つ話し終えたときでも会話の糸口を作りやすくなります。"
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)
            with patch.object(bank,"generate",return_value=[{"hook":text.splitlines()[0],"body":text.splitlines()[1]}]) as fake:
                result=bank.run("liver_manager",1,folder)
            self.assertEqual(fake.call_count,1)
            self.assertEqual(result["draft_count"],1)
            self.assertEqual(result["ready_count"],0)
            self.assertEqual(result["sheets_writes"],0)
            self.assertEqual(result["posts"],0)
            artifact=folder/"liver_manager-pending-qa.json"
            doc=json.loads(artifact.read_text())
            self.assertEqual(doc["status"],"PENDING_HUMAN_QA")
            self.assertFalse(doc["canonical_bank_ready"])
            self.assertEqual(doc["candidates"][0]["workflow_status"],"PENDING_HUMAN_QA")
            self.assertEqual(os.stat(artifact).st_mode & 0o777,0o600)

    def test_symlink_and_invalid_account(self):
        with tempfile.TemporaryDirectory() as base:
            with self.assertRaises(ValueError):
                bank.run("beauty_account",5,Path(base))
            link=Path(base)/"link"
            link.symlink_to(base)
            with self.assertRaises(ValueError):
                bank.run("night_scout",5,link)

    def test_invalid_model_output_is_rejected_without_false_progress(self):
        text="ライブを頑張りましょう。"
        with tempfile.TemporaryDirectory() as root,patch.object(
            bank,"generate",side_effect=[[{"hook":"X","body":text}],[]]*13
        ):
            result=bank.run("liver_manager",2,Path(root))
        self.assertEqual(result["draft_count"],0)
        self.assertEqual(result["status"],"PENDING_HUMAN_QA")


if __name__=="__main__":
    unittest.main()
