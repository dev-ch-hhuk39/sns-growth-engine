#!/usr/bin/env python3
"""Offline assertions: pinned, private, reference-only public trend previews."""
from __future__ import annotations

import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import sns_local_source_research_preview as mod


class SourcePreviewTests(unittest.TestCase):
    def test_extract_json_with_preamble(self):
        data = mod.extract_json('PREAMBLE\n{"results":[{"url":"https://example.com/ok"}],"clusters":[]}\n')
        self.assertEqual(len(data["results"]),1)
        with self.assertRaises(mod.ResearchBlocked):
            mod.extract_json('private unstructured text')

    def test_reference_only_filters_unsafe_url(self):
        rows=[
            {"url":"http://example.org","title":"bad"},
            {"url":"https://localhost/nope","title":"bad"},
            {"url":"https://user:pass@example.org/nope","title":"bad"},
            {"url":"https://www.reddit.com/r/test/comments/123","title":"Topic","summary":"Learn","source":"reddit"},
        ]
        picked=mod.evidence(rows,"night_scout",True)
        self.assertEqual(len(picked),1)
        self.assertEqual(picked[0]["status"],"WAITING_REVIEW")
        self.assertEqual(picked[0]["rights_policy"],"reference_only")
        self.assertEqual(picked[0]["media_policy"],"do_not_download")
        self.assertTrue(picked[0]["fallback_general_topic"])

    def test_primary_empty_falls_back_and_persists_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            folder.chmod(0o700)
            response={"results":[{"url":"https://news.ycombinator.com/item?id=222","title":"Research example"}],"clusters":[]}
            with patch.object(mod,"search",side_effect=[{"results":[],"clusters":[]},response,
                                                      response,response]) as finder:
                out=mod.run(Path("/mock-pinned-script"),output_dir=folder)
            self.assertEqual(out["status"],"PASS")
            self.assertEqual(out["accounts"]["night_scout"],1)
            self.assertEqual(out["accounts"]["liver_manager"],1)
            self.assertEqual(finder.call_count,3)
            files=list(folder.glob("daily-*.json"))
            self.assertEqual(len(files),1)
            self.assertEqual(stat.S_IMODE(files[0].stat().st_mode),0o600)
            data=json.loads(files[0].read_text())
            self.assertEqual(data["posts"],0)
            self.assertEqual(data["paid_ai"],0)
            self.assertEqual(data["sheets_writes"],0)

    def test_symlink_target_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as parent:
            link=Path(parent)/"previews"
            link.symlink_to(tmp, target_is_directory=True)
            with patch.object(mod,"search",return_value={"results":[],"clusters":[]}) as fn:
                with self.assertRaises(mod.ResearchBlocked):
                    mod.run(Path("/fake"),output_dir=link)
            self.assertGreaterEqual(fn.call_count,2)


if __name__=="__main__":
    unittest.main()
