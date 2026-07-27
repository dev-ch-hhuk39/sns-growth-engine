#!/usr/bin/env python3
import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock
from io import StringIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.join(ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "src"))

from src.youtube_path_provenance import (
    analyse_youtube_url,
    PathShape,
    TabKind,
    PostKind,
    shape_to_safe_dict,
)
import inspect_wp3c5_youtube_path_provenance as _inspector_mod
from inspect_wp3c5_youtube_path_provenance import main, _analyse, TARGET_SOURCE_POST_ID, _build_fail_result

class TestWP3C5YouTubePathProvenance(unittest.TestCase):
    def setUp(self):
        pass

    @patch("inspect_wp3c5_youtube_path_provenance.check_safety_flags", return_value=True)
    @patch("inspect_wp3c5_youtube_path_provenance.SheetsClient")
    def test_unsafe_flag(self, mock_client, mock_check_flags):
        test_args = ["prog", "--output", "test_out.json"]
        with patch.object(sys, "argv", test_args):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 1)
            
        with open("test_out.json", "r") as f:
            data = json.load(f)
            self.assertEqual(data["overall_status"], "FAIL")
            self.assertIn("UNSAFE_FLAG_ENABLED", data["status_reasons"])
            self.assertEqual(data["classification"], "MIXED_OR_UNRESOLVED")
            self.assertFalse(data["static_trace"]["current_parent_id_uses_source_and_external_id"])
        
        os.remove("test_out.json")

    @patch("inspect_wp3c5_youtube_path_provenance.check_safety_flags", return_value=False)
    @patch("inspect_wp3c5_youtube_path_provenance.get_config")
    def test_client_init_fail(self, mock_get_config, mock_check_flags):
        mock_get_config.side_effect = Exception("Config error")
        
        test_args = ["prog", "--output", "test_out.json"]
        with patch.object(sys, "argv", test_args):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 1)
            
        with open("test_out.json", "r") as f:
            data = json.load(f)
            self.assertEqual(data["overall_status"], "FAIL")
            self.assertIn("CLIENT_INITIALIZATION_FAILED", data["status_reasons"])
            
        os.remove("test_out.json")

    @patch("inspect_wp3c5_youtube_path_provenance.check_safety_flags", return_value=False)
    @patch("inspect_wp3c5_youtube_path_provenance.get_config")
    @patch("inspect_wp3c5_youtube_path_provenance.SheetsClient")
    def test_worksheet_read_fail(self, mock_client_cls, mock_get_config, mock_check_flags):
        mock_get_config.return_value = {"sheet_id": "abc", "sa_dict": {}}
        mock_client = MagicMock()
        mock_client._ws.side_effect = Exception("WS error")
        mock_client_cls.return_value = mock_client
        
        test_args = ["prog", "--output", "test_out.json"]
        with patch.object(sys, "argv", test_args):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 1)
            
        with open("test_out.json", "r") as f:
            data = json.load(f)
            self.assertEqual(data["overall_status"], "FAIL")
            self.assertIn("WORKSHEET_READ_FAILED", data["status_reasons"])
            
        os.remove("test_out.json")

    @patch("inspect_wp3c5_youtube_path_provenance.check_safety_flags", return_value=False)
    @patch("inspect_wp3c5_youtube_path_provenance.get_config")
    @patch("inspect_wp3c5_youtube_path_provenance.SheetsClient")
    @patch("inspect_wp3c5_youtube_path_provenance.read_rows_with_sheet_numbers")
    @patch("inspect_wp3c5_youtube_path_provenance._analyse")
    def test_analysis_fail(self, mock_analyse, mock_read, mock_client_cls, mock_get_config, mock_check_flags):
        mock_read.return_value = []
        mock_get_config.return_value = {"sheet_id": "abc", "sa_dict": {}}
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_analyse.side_effect = Exception("Analysis error")
        
        test_args = ["prog", "--output", "test_out.json"]
        with patch.object(sys, "argv", test_args):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 1)
            
        with open("test_out.json", "r") as f:
            data = json.load(f)
            self.assertEqual(data["overall_status"], "FAIL")
            self.assertIn("ANALYSIS_FAILED", data["status_reasons"])
            
        os.remove("test_out.json")

    def _make_mock_parent(self, url, ext_id="ext1", src_id="src1", acc_id="acc1", media_count=0):
        return {
            "source_post_id": TARGET_SOURCE_POST_ID,
            "canonical_post_url": url,
            "external_post_id": ext_id,
            "source_id": src_id,
            "source_account_id": acc_id,
            "discovered_at": "2024-01-01T00:00:00Z",
            "created_at": "2024-01-01T00:00:00Z",
            "media_count": str(media_count),
            "platform": "YOUTUBE",
            "source_type": "CHANNEL",
            "content_type": "VIDEO"
        }

    def _make_mock_child(self, url, media_url="http://media.com/1", child_id="child1", m_idx=0, m_type="image", acq="MANUAL"):
        return {
            "source_post_id": TARGET_SOURCE_POST_ID,
            "source_post_media_id": child_id,
            "canonical_post_url": url,
            "original_media_url": media_url,
            "created_at": "2024-01-01T00:00:00Z",
            "media_index": str(m_idx),
            "media_type": m_type,
            "acquisition_method": acq,
        }

    def test_historical_channel_tab_pseudo_entries(self):
        parents = [
            (1, self._make_mock_parent("https://youtube.com/@h/videos")),
            (2, self._make_mock_parent("https://youtube.com/@h/shorts")),
            (3, self._make_mock_parent("https://youtube.com/@h/streams")),
        ]
        children = [
            (4, self._make_mock_child("https://youtube.com/@h/videos", media_url="url1", child_id="c1", m_idx=0)),
            (5, self._make_mock_child("https://youtube.com/@h/shorts", media_url="url2", child_id="c1", m_idx=0)),
            (6, self._make_mock_child("https://youtube.com/@h/streams", media_url="url3", child_id="c1", m_idx=0)),
        ]
        res = _analyse(parents, children, "0"*40)
        self.assertEqual(res["classification"], "HISTORICAL_CHANNEL_TAB_PSEUDO_ENTRIES")
        self.assertEqual(res["recommended_next_action"], "PLAN_HISTORICAL_PSEUDO_ENTRY_REPAIR_REVIEW")
        self.assertEqual(res["counts"]["parent_child_url_group_match_count"], 3)
        self.assertEqual(res["counts"]["unique_parent_canonical_url_group_count"], 3)
        self.assertEqual(res["counts"]["unique_child_canonical_url_group_count"], 3)
        self.assertEqual(res["counts"]["unique_external_post_id_group_count"], 1)
        self.assertEqual(res["counts"]["unique_source_id_group_count"], 1)
        self.assertEqual(res["counts"]["unique_child_id_group_count"], 1)
        self.assertEqual(res["apply_operations"], [])
        self.assertEqual(len(set(p["semantic_parent_group"] for p in res["parents"])), 1)

    def test_account_page_collision_confirmed(self):
        # Fail unique child ID
        parents = [
            (1, self._make_mock_parent("https://youtube.com/@h/videos")),
            (2, self._make_mock_parent("https://youtube.com/@h/shorts")),
            (3, self._make_mock_parent("https://youtube.com/@h/streams")),
        ]
        children = [
            (4, self._make_mock_child("https://youtube.com/@h/videos", media_url="url1", child_id="c1", m_idx=0)),
            (5, self._make_mock_child("https://youtube.com/@h/shorts", media_url="url2", child_id="c2", m_idx=0)),
            (6, self._make_mock_child("https://youtube.com/@h/streams", media_url="url3", child_id="c3", m_idx=0)),
        ]
        res = _analyse(parents, children, "0"*40)
        self.assertEqual(res["classification"], "ACCOUNT_PAGE_COLLISION_CONFIRMED")
        
        # parent 0件
        res = _analyse([], children, "0"*40)
        self.assertEqual(res["classification"], "MIXED_OR_UNRESOLVED")
        
        # child 0件
        res = _analyse(parents, [], "0"*40)
        self.assertEqual(res["classification"], "MIXED_OR_UNRESOLVED")

    def test_nonpost_youtube_url_collision(self):
        parents = [
            (1, self._make_mock_parent("https://youtube.com/playlist?list=123")),
        ]
        children = [
            (4, self._make_mock_child("https://youtube.com/playlist?list=123")),
        ]
        res = _analyse(parents, children, "0"*40)
        self.assertEqual(res["classification"], "NONPOST_YOUTUBE_URL_COLLISION")

    def test_mixed_or_unresolved(self):
        parents = [
            (1, self._make_mock_parent("https://youtube.com/watch?v=123")), # POST URL
        ]
        children = [
            (4, self._make_mock_child("https://youtube.com/watch?v=123")),
        ]
        res = _analyse(parents, children, "0"*40)
        self.assertEqual(res["classification"], "MIXED_OR_UNRESOLVED")

    def test_parent_child_canonical_group_mismatch(self):
        parents = [
            (1, self._make_mock_parent("https://youtube.com/@h/videos")),
            (2, self._make_mock_parent("https://youtube.com/@h/shorts")),
            (3, self._make_mock_parent("https://youtube.com/@h/streams")),
        ]
        children = [
            (4, self._make_mock_child("https://youtube.com/@h/videos")),
            (5, self._make_mock_child("https://youtube.com/@h/shorts")),
            (6, self._make_mock_child("https://youtube.com/@h/DIFFERENT")),
        ]
        res = _analyse(parents, children, "0"*40)
        self.assertEqual(res["classification"], "ACCOUNT_PAGE_COLLISION_CONFIRMED")

    def test_tab_kind_1_type_only(self):
        parents = [
            (1, self._make_mock_parent("https://youtube.com/@h/videos")),
            (2, self._make_mock_parent("https://youtube.com/@h/videos")),
            (3, self._make_mock_parent("https://youtube.com/@h/videos")),
        ]
        children = [
            (4, self._make_mock_child("https://youtube.com/@h/videos")),
            (5, self._make_mock_child("https://youtube.com/@h/videos")),
            (6, self._make_mock_child("https://youtube.com/@h/videos")),
        ]
        res = _analyse(parents, children, "0"*40)
        self.assertEqual(res["classification"], "ACCOUNT_PAGE_COLLISION_CONFIRMED")
        
    def test_parent_semantic_group_2_types(self):
        parents = [
            (1, self._make_mock_parent("https://youtube.com/@h/videos", src_id="src1")),
            (2, self._make_mock_parent("https://youtube.com/@h/shorts", src_id="src2")),
            (3, self._make_mock_parent("https://youtube.com/@h/streams", src_id="src1")),
        ]
        children = [
            (4, self._make_mock_child("https://youtube.com/@h/videos", media_url="url1", child_id="c1", m_idx=0)),
            (5, self._make_mock_child("https://youtube.com/@h/shorts", media_url="url2", child_id="c1", m_idx=0)),
            (6, self._make_mock_child("https://youtube.com/@h/streams", media_url="url3", child_id="c1", m_idx=0)),
        ]
        res = _analyse(parents, children, "0"*40)
        self.assertEqual(res["classification"], "ACCOUNT_PAGE_COLLISION_CONFIRMED")
        
    def test_child_id_group_2_types(self):
        parents = [
            (1, self._make_mock_parent("https://youtube.com/@h/videos")),
            (2, self._make_mock_parent("https://youtube.com/@h/shorts")),
            (3, self._make_mock_parent("https://youtube.com/@h/streams")),
        ]
        children = [
            (4, self._make_mock_child("https://youtube.com/@h/videos", media_url="url1", child_id="c1", m_idx=0)),
            (5, self._make_mock_child("https://youtube.com/@h/shorts", media_url="url2", child_id="c2", m_idx=0)),
            (6, self._make_mock_child("https://youtube.com/@h/streams", media_url="url3", child_id="c1", m_idx=0)),
        ]
        res = _analyse(parents, children, "0"*40)
        self.assertEqual(res["classification"], "ACCOUNT_PAGE_COLLISION_CONFIRMED")
        
    def test_media_index_not_0(self):
        parents = [
            (1, self._make_mock_parent("https://youtube.com/@h/videos")),
            (2, self._make_mock_parent("https://youtube.com/@h/shorts")),
            (3, self._make_mock_parent("https://youtube.com/@h/streams")),
        ]
        children = [
            (4, self._make_mock_child("https://youtube.com/@h/videos", media_url="url1", child_id="c1", m_idx=1)),
            (5, self._make_mock_child("https://youtube.com/@h/shorts", media_url="url2", child_id="c1", m_idx=0)),
            (6, self._make_mock_child("https://youtube.com/@h/streams", media_url="url3", child_id="c1", m_idx=0)),
        ]
        res = _analyse(parents, children, "0"*40)
        self.assertEqual(res["classification"], "ACCOUNT_PAGE_COLLISION_CONFIRMED")

    def test_original_media_url_group_1_type_only(self):
        parents = [
            (1, self._make_mock_parent("https://youtube.com/@h/videos")),
            (2, self._make_mock_parent("https://youtube.com/@h/shorts")),
            (3, self._make_mock_parent("https://youtube.com/@h/streams")),
        ]
        children = [
            (4, self._make_mock_child("https://youtube.com/@h/videos", media_url="url1", child_id="c1", m_idx=0)),
            (5, self._make_mock_child("https://youtube.com/@h/shorts", media_url="url1", child_id="c1", m_idx=0)),
            (6, self._make_mock_child("https://youtube.com/@h/streams", media_url="url1", child_id="c1", m_idx=0)),
        ]
        res = _analyse(parents, children, "0"*40)
        self.assertEqual(res["classification"], "ACCOUNT_PAGE_COLLISION_CONFIRMED")


    @patch("inspect_wp3c5_youtube_path_provenance.check_safety_flags", return_value=False)
    @patch("inspect_wp3c5_youtube_path_provenance.get_config")
    @patch("inspect_wp3c5_youtube_path_provenance.SheetsClient")
    def test_sheets_client_contract(self, mock_sc_class, mock_get_config, mock_check_flags):
        mock_get_config.return_value = {"sheet_id": "test_sheet_id", "sa_dict": {"test": "dict"}}
        mock_client = MagicMock()
        mock_sc_class.return_value = mock_client
        mock_ws_posts = MagicMock()
        mock_ws_media = MagicMock()
        mock_client._ws.side_effect = lambda n: mock_ws_posts if n == "source_posts" else mock_ws_media
        mock_ws_posts.get_all_values.return_value = []
        mock_ws_media.get_all_values.return_value = []
        
        test_args = ["prog", "--output", "test_out.json"]
        with patch.object(sys, "argv", test_args):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 0)

        mock_sc_class.assert_called_once_with("test_sheet_id", {"test": "dict"}, dry_run=True)
        self.assertEqual(mock_client._ws.call_count, 2)
        mock_client._ws.assert_any_call("source_posts")
        mock_client._ws.assert_any_call("source_post_media")
        mock_ws_posts.get_all_values.assert_called_once_with()
        mock_ws_media.get_all_values.assert_called_once_with()
        
        # verify prevent_writes installed bomb on write methods for mock_client and worksheets
        # (prevent_writes replaces them with a bomb function - calling them raises Exception)
        for prevent_target in [mock_client, mock_ws_posts, mock_ws_media]:
            for method_name in ["_ensure_tab", "append_row", "append_rows", "update",
                                "update_cell", "resize", "clear", "delete_rows"]:
                method = getattr(prevent_target, method_name)
                if not hasattr(method, "call_count"):
                    # bomb function installed by prevent_writes - calling raises Exception
                    with self.assertRaises(Exception):
                        method()
                else:
                    # still a MagicMock - should not have been called
                    self.assertEqual(method.call_count, 0, f"{method_name} was called")
        
        if os.path.exists("test_out.json"):
            os.remove("test_out.json")

    @patch("inspect_wp3c5_youtube_path_provenance.check_safety_flags", return_value=False)
    @patch("inspect_wp3c5_youtube_path_provenance.get_config")
    @patch("inspect_wp3c5_youtube_path_provenance.SheetsClient")
    def test_fail_non_leakage(self, mock_sc_class, mock_get_config, mock_check_flags):
        mock_get_config.return_value = {"sheet_id": "test_sheet_id", "sa_dict": {"test": "dict"}}
        
        cases = [
            ("CLIENT_SECRET_EXCEPTION_TEXT", Exception("CLIENT_SECRET_EXCEPTION_TEXT"), None),
            ("WORKSHEET_SECRET_EXCEPTION_TEXT", None, Exception("WORKSHEET_SECRET_EXCEPTION_TEXT")),
        ]
        
        for keyword, client_ex, ws_ex in cases:
            mock_client = MagicMock()
            if client_ex:
                mock_sc_class.side_effect = client_ex
            else:
                mock_sc_class.side_effect = None
                mock_sc_class.return_value = mock_client
                if ws_ex:
                    mock_client._ws.side_effect = ws_ex
                
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout, \
                 patch("sys.stderr", new_callable=StringIO) as mock_stderr, \
                 patch.object(sys, "argv", ["prog", "--output", "test_out.json"]):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)

                out = mock_stdout.getvalue()
                err = mock_stderr.getvalue()
                
                self.assertNotIn(keyword, out)
                self.assertNotIn(keyword, err)
                
                import re
                m = re.search(r"^WP3C5_SAFE_YOUTUBE_PATH_PROVENANCE_JSON=(.*)", out, re.MULTILINE)
                self.assertIsNotNone(m)
                j = json.loads(m.group(1))
                self.assertEqual(j["parents"], [])
                self.assertEqual(j["children"], [])
                self.assertEqual(j["apply_operations"], [])
                self.assertNotIn(keyword, json.dumps(j))

class TestWP3C5Renderer(unittest.TestCase):
    def test_renderer_success(self):
        import render_wp3c5_youtube_path_provenance_summary as renderer
        data = {
            "schema_version": 1,
            "mode": "READ_ONLY_SAFE_YOUTUBE_PATH_PROVENANCE",
            "overall_status": "READY_FOR_MANUAL_DECISION",
            "classification": "HISTORICAL_CHANNEL_TAB_PSEUDO_ENTRIES",
            "status_reasons": ["HISTORICAL_CHANNEL_TAB_PSEUDO_ENTRIES"],
            "checked_commit_sha": "0"*40,
            "counts": {
                "parent_count": 0,
                "child_count": 0,
                "unique_external_post_id_group_count": 0,
                "unique_source_id_group_count": 0,
                "unique_child_id_group_count": 0,
                "unique_parent_canonical_url_group_count": 0,
                "unique_child_canonical_url_group_count": 0,
                "unique_child_original_media_url_group_count": 0,
                "unique_parent_tab_kind_count": 0,
                "unique_child_tab_kind_count": 0,
                "parent_child_url_group_match_count": 0,
                "parent_child_row_number_match_count": 0,
                "unique_parent_recovered_group_count": 0,
                "unique_child_recovered_group_count": 0,
            },
            "static_trace": {
                "current_parent_id_uses_source_and_external_id": False,
                "current_child_id_uses_parent_and_media_index": False,
                "current_discovery_rejects_nonpost_youtube_urls": False,
                "current_discovery_handles_channel_landing_pages": False,
                "candidate_historical_writer_count": 0,
                "candidate_historical_writer_labels": []
            },
            "parents": [],
            "children": [],
            "recommended_next_action": "PLAN_HISTORICAL_PSEUDO_ENTRY_REPAIR_REVIEW",
            "apply_operations": []
        }
        renderer.validate_contract(data, 0)
        
    def test_renderer_fail(self):
        import render_wp3c5_youtube_path_provenance_summary as renderer
        data = {
            "schema_version": 1,
            "mode": "READ_ONLY_SAFE_YOUTUBE_PATH_PROVENANCE",
            "overall_status": "FAIL",
            "classification": "MIXED_OR_UNRESOLVED",
            "status_reasons": ["INSPECTOR_STARTUP_FAILED"],
            "checked_commit_sha": "0"*40,
            "counts": {
                "parent_count": 0,
                "child_count": 0,
                "unique_external_post_id_group_count": 0,
                "unique_source_id_group_count": 0,
                "unique_child_id_group_count": 0,
                "unique_parent_canonical_url_group_count": 0,
                "unique_child_canonical_url_group_count": 0,
                "unique_child_original_media_url_group_count": 0,
                "unique_parent_tab_kind_count": 0,
                "unique_child_tab_kind_count": 0,
                "parent_child_url_group_match_count": 0,
                "parent_child_row_number_match_count": 0,
                "unique_parent_recovered_group_count": 0,
                "unique_child_recovered_group_count": 0,
            },
            "static_trace": {
                "current_parent_id_uses_source_and_external_id": False,
                "current_child_id_uses_parent_and_media_index": False,
                "current_discovery_rejects_nonpost_youtube_urls": False,
                "current_discovery_handles_channel_landing_pages": False,
                "candidate_historical_writer_count": 0,
                "candidate_historical_writer_labels": []
            },
            "parents": [],
            "children": [],
            "recommended_next_action": "MANUAL_INVESTIGATION",
            "apply_operations": []
        }
        renderer.validate_contract(data, 1)

    def test_renderer_rejects(self):
        import render_wp3c5_youtube_path_provenance_summary as renderer
        data = {
            "schema_version": 1,
            "mode": "READ_ONLY_SAFE_YOUTUBE_PATH_PROVENANCE",
            "overall_status": "READY_FOR_MANUAL_DECISION",
            "classification": "HISTORICAL_CHANNEL_TAB_PSEUDO_ENTRIES",
            "status_reasons": ["HISTORICAL_CHANNEL_TAB_PSEUDO_ENTRIES"],
            "checked_commit_sha": "0"*40,
            "counts": {
                "parent_count": 0,
                "child_count": 0,
                "unique_external_post_id_group_count": 0,
                "unique_source_id_group_count": 0,
                "unique_child_id_group_count": 0,
                "unique_parent_canonical_url_group_count": 0,
                "unique_child_canonical_url_group_count": 0,
                "unique_child_original_media_url_group_count": 0,
                "unique_parent_tab_kind_count": 0,
                "unique_child_tab_kind_count": 0,
                "parent_child_url_group_match_count": 0,
                "parent_child_row_number_match_count": 0,
                "unique_parent_recovered_group_count": 0,
                "unique_child_recovered_group_count": 0,
            },
            "static_trace": {
                "current_parent_id_uses_source_and_external_id": False,
                "current_child_id_uses_parent_and_media_index": False,
                "current_discovery_rejects_nonpost_youtube_urls": False,
                "current_discovery_handles_channel_landing_pages": False,
                "candidate_historical_writer_count": 0,
                "candidate_historical_writer_labels": []
            },
            "parents": [],
            "children": [],
            "recommended_next_action": "PLAN_HISTORICAL_PSEUDO_ENTRY_REPAIR_REVIEW",
            "apply_operations": []
        }
        
        # READY + exit 1 -> reject
        with self.assertRaises(ValueError):
            renderer.validate_contract(data, 1)
            
        data["overall_status"] = "FAIL"
        data["classification"] = "MIXED_OR_UNRESOLVED"
        data["recommended_next_action"] = "MANUAL_INVESTIGATION"
        # FAIL + exit 0 -> reject
        with self.assertRaises(ValueError):
            renderer.validate_contract(data, 0)
            
        data["overall_status"] = "READY_FOR_MANUAL_DECISION"
        data["classification"] = "HISTORICAL_CHANNEL_TAB_PSEUDO_ENTRIES"
        data["recommended_next_action"] = "PLAN_HISTORICAL_PSEUDO_ENTRY_REPAIR_REVIEW"
        
        # root extra key
        d2 = data.copy()
        d2["extra"] = 1
        with self.assertRaises(ValueError):
            renderer.validate_contract(d2, 0)
            
        # URL reject
        d3 = data.copy()
        d3["status_reasons"] = ["https://youtube.com"]
        with self.assertRaises(ValueError):
            renderer.validate_contract(d3, 0)
            
        # bool as int reject (counts)
        d4 = data.copy()
        d4["counts"] = data["counts"].copy()
        d4["counts"]["parent_count"] = True
        with self.assertRaises(ValueError):
            renderer.validate_contract(d4, 0)
            
    def test_renderer_main_no_raw_exception(self):
        import subprocess, sys, os, tempfile, json
        data = {"invalid": True}
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            json.dump(data, f)
            name = f.name
            
        try:
            renderer_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "render_wp3c5_youtube_path_provenance_summary.py")
            res = subprocess.run([sys.executable, renderer_path, "--json-file", name, "--exit-code", "0"], capture_output=True, text=True)
            self.assertEqual(res.returncode, 1)
            self.assertEqual(res.stderr.strip(), "WP3-C5 summary renderer failed: ValueError")
            self.assertEqual(res.stdout.strip(), "")
        finally:
            os.remove(name)


if __name__ == "__main__":
    unittest.main()
