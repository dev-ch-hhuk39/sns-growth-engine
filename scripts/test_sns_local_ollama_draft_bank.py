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
    def test_local_inference_disables_proxies_and_redirects(self):
        from unittest.mock import MagicMock
        response = MagicMock(status=200)
        response.read.return_value = b'{"response":"{\\"posts\\":[]}"}'
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with patch.object(bank.urllib.request, 'build_opener', return_value=opener) as build:
            self.assertEqual(bank.generate('liver_manager', {}, 1, 0), [])
        handlers = build.call_args.args
        self.assertIsInstance(handlers[0], bank.NoRedirect)
        self.assertIsInstance(handlers[1], bank.urllib.request.ProxyHandler)
        self.assertEqual(handlers[1].proxies, {})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'http://127.0.0.1:11434/api/generate')
        with self.assertRaisesRegex(ValueError, 'LOCAL_INFERENCE_REDIRECT_BLOCKED'):
            handlers[0].redirect_request(request, None, 302, '', {}, 'https://example.com')

    def test_cloud_model_or_invalid_batch_budget_cannot_reach_inference(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(bank, 'generate') as model:
            for kwargs in ({'model':'other:cloud'}, {'max_batches':0}, {'max_batches':26}, {'max_batches':True}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    bank.run('night_scout', 1, Path(temporary), **kwargs)
        model.assert_not_called()
        with patch.object(bank.urllib.request,'build_opener') as network, self.assertRaises(ValueError):
            bank.generate('night_scout',{},1,0,model='other:cloud')
        network.assert_not_called()

    def test_installed_large_model_and_short_budget_stay_pending(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(bank,'generate',return_value=[]) as model:
            result=bank.run('liver_manager',2,Path(temporary),model='gemma4:26b',max_batches=3)
        self.assertEqual(model.call_count,3)
        self.assertTrue(all(call.kwargs['model']=='gemma4:26b' for call in model.call_args_list))
        self.assertEqual(result['model_calls'],3)
        self.assertEqual(result['model'],'gemma4:26b')
        self.assertEqual(result['ready_count'],0)
        self.assertEqual(result['paid_api_calls'],0)

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
