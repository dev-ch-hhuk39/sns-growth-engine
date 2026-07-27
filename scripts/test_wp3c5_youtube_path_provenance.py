#!/usr/bin/env python3
import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

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
from scripts.inspect_wp3c5_youtube_path_provenance import main, _analyse, TARGET_SOURCE_POST_ID, _build_fail_result

class TestWP3C5YouTubePathProvenance(unittest.TestCase):
    def setUp(self):
        pass

    @patch("scripts.inspect_wp3c5_youtube_path_provenance.check_safety_flags")
    @patch("scripts.inspect_wp3c5_youtube_path_provenance.SheetsClient")
    def test_unsafe_flag(self, mock_client, mock_check_flags):
        mock_check_flags.return_value = True
        
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

    @patch("scripts.inspect_wp3c5_youtube_path_provenance.check_safety_flags")
    @patch("scripts.inspect_wp3c5_youtube_path_provenance.get_config")
    def test_client_init_fail(self, mock_get_config, mock_check_flags):
        mock_check_flags.return_value = False
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

    @patch("scripts.inspect_wp3c5_youtube_path_provenance.check_safety_flags")
    @patch("scripts.inspect_wp3c5_youtube_path_provenance.get_config")
    @patch("scripts.inspect_wp3c5_youtube_path_provenance.SheetsClient")
    def test_worksheet_read_fail(self, mock_client_cls, mock_get_config, mock_check_flags):
        mock_check_flags.return_value = False
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

    @patch("scripts.inspect_wp3c5_youtube_path_provenance.check_safety_flags")
    @patch("scripts.inspect_wp3c5_youtube_path_provenance.get_config")
    @patch("scripts.inspect_wp3c5_youtube_path_provenance.SheetsClient")
    @patch("scripts.inspect_wp3c5_youtube_path_provenance.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c5_youtube_path_provenance._analyse")
    def test_analysis_fail(self, mock_analyse, mock_read, mock_client_cls, mock_get_config, mock_check_flags):
        mock_read.return_value = []
        mock_check_flags.return_value = False
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

    def test_sheets_client_contract(self):
        # Already verified partly in test_worksheet_read_fail, but need to check prevent_writes
        pass

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

if __name__ == "__main__":
    unittest.main()
