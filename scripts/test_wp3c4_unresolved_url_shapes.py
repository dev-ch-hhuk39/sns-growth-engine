import os
import sys
import unittest
import json
import tempfile
import subprocess
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.sheets_client import SheetsClient
from scripts.inspect_wp3c4_unresolved_url_shapes import main, TARGET_SOURCE_POST_ID
from src.url_shape_diagnostics import normalize_url_for_safe_grouping

class TestWP3C4UnresolvedUrlShapes(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {"GITHUB_SHA": "1234567890123456789012345678901234567890"})
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    def create_mock_sheets(self, parents, children):
        mock_client = unittest.mock.MagicMock()
        mock_source_posts_ws = unittest.mock.MagicMock()
        mock_source_post_media_ws = unittest.mock.MagicMock()
        
        mock_client.get_worksheet.side_effect = lambda n: mock_source_posts_ws if n == "source_posts" else mock_source_post_media_ws
        
        def fake_read_rows(ws):
            if ws == mock_source_posts_ws:
                return parents
            return children
            
        return mock_client, fake_read_rows

    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_unsafe_flag_stops_before_sheets(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = True
        with self.assertRaises(SystemExit) as cm:
            with patch("sys.argv", ["script", "--output", "out.json"]):
                main()
        self.assertEqual(cm.exception.code, 1)
        mock_sheets.assert_not_called()

    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_recoverable_same_post(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/watch?v=11111111111", "media_count": 2, "platform": "youtube", "source_type": "url", "content_type": "video"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/11111111111", "media_count": 2, "platform": "youtube", "source_type": "url", "content_type": "video"})
        ]
        children = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "spm_1_0", "media_index": 0, "canonical_post_url": "https://youtube.com/watch?v=11111111111", "media_type": "video", "original_media_url": "https://cdn.example/1.mp4"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "spm_1_1", "media_index": 1, "canonical_post_url": "https://youtube.com/watch?v=11111111111", "media_type": "video", "original_media_url": "https://cdn.example/2.mp4"}),
            (4, {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "spm_2_0", "media_index": 0, "canonical_post_url": "https://youtu.be/11111111111", "media_type": "video", "original_media_url": "https://cdn.example/1.mp4"}),
            (5, {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "spm_2_1", "media_index": 1, "canonical_post_url": "https://youtu.be/11111111111", "media_type": "video", "original_media_url": "https://cdn.example/2.mp4"})
        ]
        
        mock_sheets.return_value, fake_read = self.create_mock_sheets(parents, children)
        mock_read.side_effect = fake_read
        
        with patch("sys.argv", ["script", "--output", "out.json"]):
            from io import StringIO
            captured = StringIO()
            sys.stdout = captured
            main()
            sys.stdout = sys.__stdout__
            
            output = captured.getvalue()
            self.assertIn("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=", output)
            json_str = output.split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1]
            data = json.loads(json_str)
            self.assertEqual(data["classification"], "RECOVERABLE_SAME_POST")
            
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_recoverable_distinct_posts(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/watch?v=11111111111", "media_count": 1, "platform": "youtube", "source_type": "url", "content_type": "video"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/watch?v=22222222222", "media_count": 1, "platform": "youtube", "source_type": "url", "content_type": "video"})
        ]
        children = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "spm_1_0", "media_index": 0, "canonical_post_url": "https://youtube.com/watch?v=11111111111", "media_type": "video", "original_media_url": "https://cdn.example/1.mp4"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "spm_2_0", "media_index": 0, "canonical_post_url": "https://youtube.com/watch?v=22222222222", "media_type": "video", "original_media_url": "https://cdn.example/2.mp4"}),
        ]
        
        mock_sheets.return_value, fake_read = self.create_mock_sheets(parents, children)
        mock_read.side_effect = fake_read
        
        with patch("sys.argv", ["script", "--output", "out.json"]):
            from io import StringIO
            captured = StringIO()
            sys.stdout = captured
            main()
            sys.stdout = sys.__stdout__
            
            output = captured.getvalue()
            json_str = output.split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1]
            data = json.loads(json_str)
            self.assertEqual(data["classification"], "RECOVERABLE_DISTINCT_POSTS")

    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_account_or_channel_urls(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/channel/123", "media_count": 1}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/@user", "media_count": 1})
        ]
        children = [(2, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0})]
        mock_sheets.return_value, fake_read = self.create_mock_sheets(parents, children)
        mock_read.side_effect = fake_read
        with patch("sys.argv", ["script", "--output", "out.json"]):
            from io import StringIO
            captured = StringIO()
            sys.stdout = captured
            main()
            sys.stdout = sys.__stdout__
            data = json.loads(captured.getvalue().split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1])
            self.assertEqual(data["classification"], "ACCOUNT_OR_CHANNEL_URLS")

    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_wrapped_or_encoded_urls(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        parents = [(2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://google.com/url?q=https%3A%2F%2Fexample.com", "media_count": 1})]
        children = [(2, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0})]
        mock_sheets.return_value, fake_read = self.create_mock_sheets(parents, children)
        mock_read.side_effect = fake_read
        with patch("sys.argv", ["script", "--output", "out.json"]):
            from io import StringIO
            captured = StringIO()
            sys.stdout = captured
            main()
            sys.stdout = sys.__stdout__
            data = json.loads(captured.getvalue().split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1])
            self.assertEqual(data["classification"], "WRAPPED_OR_ENCODED_URLS")

    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_placeholder_urls(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        parents = [(2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "placeholder_url", "media_count": 1})]
        children = [(2, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0})]
        mock_sheets.return_value, fake_read = self.create_mock_sheets(parents, children)
        mock_read.side_effect = fake_read
        with patch("sys.argv", ["script", "--output", "out.json"]):
            from io import StringIO
            captured = StringIO()
            sys.stdout = captured
            main()
            sys.stdout = sys.__stdout__
            data = json.loads(captured.getvalue().split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1])
            self.assertEqual(data["classification"], "PLACEHOLDER_OR_NONPUBLIC_URLS")

    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_mixed_unresolved_urls(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        parents = [(2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://example.com/post/1", "media_count": 1})]
        children = [(2, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0})]
        mock_sheets.return_value, fake_read = self.create_mock_sheets(parents, children)
        mock_read.side_effect = fake_read
        with patch("sys.argv", ["script", "--output", "out.json"]):
            from io import StringIO
            captured = StringIO()
            sys.stdout = captured
            main()
            sys.stdout = sys.__stdout__
            data = json.loads(captured.getvalue().split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1])
            self.assertEqual(data["classification"], "MIXED_OR_UNRESOLVED")

    def test_renderer_subprocess(self):
        with tempfile.NamedTemporaryFile("w+", delete=False) as temp_json:
            json.dump({
                "schema_version": 1,
                "mode": "READ_ONLY_SAFE_URL_SHAPE_DIAGNOSTICS",
                "overall_status": "READY_FOR_MANUAL_DECISION",
                "classification": "MIXED_OR_UNRESOLVED",
                "status_reasons": ["test"],
                "checked_commit_sha": "0" * 40,
                "parent_count": 0,
                "child_count": 0,
                "unique_parent_recovered_group_count": 0,
                "unique_child_recovered_group_count": 0,
                "unique_normalized_url_group_count": 0,
                "unique_semantic_parent_group_count": 0,
                "unique_semantic_child_group_count": 0,
                "parents": [],
                "children": [],
                "recommended_next_action": "MANUAL_INVESTIGATION",
                "apply_operations": []
            }, temp_json)
            json_path = temp_json.name
            
        with tempfile.NamedTemporaryFile("w+", delete=False) as temp_md:
            md_path = temp_md.name

        try:
            result = subprocess.run([
                sys.executable, "scripts/render_wp3c4_url_shape_summary.py",
                "--json-input", json_path,
                "--summary-output", md_path,
                "--exit-code", "0"
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            
            with open(md_path, "r") as f:
                content = f.read()
                self.assertIn("# WP3-C4 Safe URL Shape Diagnostics", content)
        finally:
            os.unlink(json_path)
            os.unlink(md_path)

if __name__ == "__main__":
    unittest.main()
