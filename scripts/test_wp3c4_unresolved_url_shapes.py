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
        parents = [(2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/watch?v=invalid12", "media_count": 1})]
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


    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_grouping_order_independent(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        parents1 = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/watch?v=1", "media_count": 1}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/watch?v=2", "media_count": 1})
        ]
        children1 = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0, "canonical_post_url": "https://youtube.com/watch?v=1"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0, "canonical_post_url": "https://youtube.com/watch?v=2"})
        ]
        mock_sheets.return_value, fake_read1 = self.create_mock_sheets(parents1, children1)
        mock_read.side_effect = fake_read1
        with patch("sys.argv", ["script", "--output", "out1.json"]):
            import io, json; captured1 = io.StringIO(); sys.stdout = captured1; from scripts.inspect_wp3c4_unresolved_url_shapes import main; main(); sys.stdout = sys.__stdout__
            data1 = json.loads(captured1.getvalue().split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1])
            
        parents2 = parents1[::-1]
        children2 = children1[::-1]
        mock_sheets.return_value, fake_read2 = self.create_mock_sheets(parents2, children2)
        mock_read.side_effect = fake_read2
        with patch("sys.argv", ["script", "--output", "out2.json"]):
            import io, json; captured2 = io.StringIO(); sys.stdout = captured2; from scripts.inspect_wp3c4_unresolved_url_shapes import main; main(); sys.stdout = sys.__stdout__
            data2 = json.loads(captured2.getvalue().split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1])
            
        self.assertEqual(data1["unique_parent_recovered_group_count"], data2["unique_parent_recovered_group_count"])
        self.assertEqual(data1["classification"], data2["classification"])

    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_safe_json_no_sensitive_data(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        hash_64 = "a" * 64
        parents = [(2, {"source_post_id": f"sp1_{hash_64}", "canonical_post_url": f"https://youtube.com/watch?v=1&token=secret_{hash_64}", "media_count": 1})]
        children = [(2, {"source_post_id": f"sp1_{hash_64}", "media_index": 0, "canonical_post_url": f"https://youtube.com/watch?v=1&token=secret_{hash_64}"})]
        mock_sheets.return_value, fake_read = self.create_mock_sheets(parents, children)
        mock_read.side_effect = fake_read
        with patch("sys.argv", ["script", "--output", "out.json"]):
            import io, json; captured = io.StringIO(); sys.stdout = captured; from scripts.inspect_wp3c4_unresolved_url_shapes import main; main(); sys.stdout = sys.__stdout__
            out_str = captured.getvalue()
            self.assertNotIn(hash_64, out_str)
            self.assertNotIn("https://", out_str)
            self.assertNotIn("token", out_str)
            self.assertNotIn("secret", out_str)
            
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_zero_parents_or_children(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        mock_sheets.return_value, fake_read = self.create_mock_sheets([], [])
        mock_read.side_effect = fake_read
        with patch("sys.argv", ["script", "--output", "out.json"]):
            import io, json; captured = io.StringIO(); sys.stdout = captured; from scripts.inspect_wp3c4_unresolved_url_shapes import main; main(); sys.stdout = sys.__stdout__
            data = json.loads(captured.getvalue().split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1])
            self.assertIn("NO_PARENT_ROWS", data["status_reasons"])
            self.assertIn("NO_CHILD_ROWS", data["status_reasons"])
            self.assertEqual(data["classification"], "MIXED_OR_UNRESOLVED")

    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_invalid_child_media_index(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        parents = [(2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/watch?v=1", "media_count": 1})]
        children = [(2, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": -1})]
        mock_sheets.return_value, fake_read = self.create_mock_sheets(parents, children)
        mock_read.side_effect = fake_read
        with patch("sys.argv", ["script", "--output", "out.json"]):
            import io, json; captured = io.StringIO(); sys.stdout = captured; from scripts.inspect_wp3c4_unresolved_url_shapes import main; main(); sys.stdout = sys.__stdout__
            data = json.loads(captured.getvalue().split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1])
            self.assertIn("INVALID_CHILD_MEDIA_INDEX", data["status_reasons"])
            
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_extra_child_identity(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        parents = [(2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/watch?v=1", "media_count": 1})]
        children = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0, "canonical_post_url": "https://youtube.com/watch?v=1"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 1, "canonical_post_url": "https://youtube.com/watch?v=2"})
        ]
        mock_sheets.return_value, fake_read = self.create_mock_sheets(parents, children)
        mock_read.side_effect = fake_read
        with patch("sys.argv", ["script", "--output", "out.json"]):
            import io, json; captured = io.StringIO(); sys.stdout = captured; from scripts.inspect_wp3c4_unresolved_url_shapes import main; main(); sys.stdout = sys.__stdout__
            data = json.loads(captured.getvalue().split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1])
            self.assertEqual(data["classification"], "MIXED_OR_UNRESOLVED")
            
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_distinct_media_index_mismatch(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/watch?v=1", "media_count": 2}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/watch?v=2", "media_count": 1})
        ]
        children = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0, "canonical_post_url": "https://youtube.com/watch?v=1"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0, "canonical_post_url": "https://youtube.com/watch?v=1"}), # duplicate 0 instead of 0, 1
            (4, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0, "canonical_post_url": "https://youtube.com/watch?v=2"})
        ]
        mock_sheets.return_value, fake_read = self.create_mock_sheets(parents, children)
        mock_read.side_effect = fake_read
        with patch("sys.argv", ["script", "--output", "out.json"]):
            import io, json; captured = io.StringIO(); sys.stdout = captured; from scripts.inspect_wp3c4_unresolved_url_shapes import main; main(); sys.stdout = sys.__stdout__
            data = json.loads(captured.getvalue().split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1])
            self.assertEqual(data["classification"], "MIXED_OR_UNRESOLVED")

    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_same_semantic_parent_mismatch(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/watch?v=1", "media_count": 1, "platform": "youtube", "source_type": "url", "content_type": "video"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/1", "media_count": 1, "platform": "youtube", "source_type": "url", "content_type": "image"})
        ]
        children = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0, "canonical_post_url": "https://youtube.com/watch?v=1"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0, "canonical_post_url": "https://youtu.be/1"})
        ]
        mock_sheets.return_value, fake_read = self.create_mock_sheets(parents, children)
        mock_read.side_effect = fake_read
        with patch("sys.argv", ["script", "--output", "out.json"]):
            import io, json; captured = io.StringIO(); sys.stdout = captured; from scripts.inspect_wp3c4_unresolved_url_shapes import main; main(); sys.stdout = sys.__stdout__
            data = json.loads(captured.getvalue().split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1])
            self.assertEqual(data["classification"], "MIXED_OR_UNRESOLVED")

    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_same_semantic_child_mismatch(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/watch?v=1", "media_count": 1, "platform": "youtube", "source_type": "url", "content_type": "video"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/1", "media_count": 1, "platform": "youtube", "source_type": "url", "content_type": "video"})
        ]
        children = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0, "canonical_post_url": "https://youtube.com/watch?v=1", "media_type": "video"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0, "canonical_post_url": "https://youtu.be/1", "media_type": "image"})
        ]
        mock_sheets.return_value, fake_read = self.create_mock_sheets(parents, children)
        mock_read.side_effect = fake_read
        with patch("sys.argv", ["script", "--output", "out.json"]):
            import io, json; captured = io.StringIO(); sys.stdout = captured; from scripts.inspect_wp3c4_unresolved_url_shapes import main; main(); sys.stdout = sys.__stdout__
            data = json.loads(captured.getvalue().split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1])
            self.assertEqual(data["classification"], "MIXED_OR_UNRESOLVED")

    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_apply_operations_empty(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        parents = [(2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/watch?v=1", "media_count": 1})]
        children = [(2, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0, "canonical_post_url": "https://youtube.com/watch?v=1"})]
        mock_sheets.return_value, fake_read = self.create_mock_sheets(parents, children)
        mock_read.side_effect = fake_read
        with patch("sys.argv", ["script", "--output", "out.json"]):
            import io, json; captured = io.StringIO(); sys.stdout = captured; from scripts.inspect_wp3c4_unresolved_url_shapes import main; main(); sys.stdout = sys.__stdout__
            data = json.loads(captured.getvalue().split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1])
            self.assertEqual(data["apply_operations"], [])
            
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.SheetsClient")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.read_rows_with_sheet_numbers")
    @patch("scripts.inspect_wp3c4_unresolved_url_shapes.check_safety_flags")
    def test_physical_row_kept(self, mock_check, mock_read, mock_sheets):
        mock_check.return_value = False
        parents = [(500, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtube.com/watch?v=1", "media_count": 1})]
        children = [(600, {"source_post_id": TARGET_SOURCE_POST_ID, "media_index": 0, "canonical_post_url": "https://youtube.com/watch?v=1"})]
        mock_sheets.return_value, fake_read = self.create_mock_sheets(parents, children)
        mock_read.side_effect = fake_read
        with patch("sys.argv", ["script", "--output", "out.json"]):
            import io, json; captured = io.StringIO(); sys.stdout = captured; from scripts.inspect_wp3c4_unresolved_url_shapes import main; main(); sys.stdout = sys.__stdout__
            data = json.loads(captured.getvalue().split("WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=")[1])
            self.assertEqual(data["parents"][0]["sheet_row_number"], 500)
            self.assertEqual(data["children"][0]["sheet_row_number"], 600)



    def valid_ready_json(self):
        return {"schema_version":1,"mode":"READ_ONLY_SAFE_URL_SHAPE_DIAGNOSTICS","overall_status":"READY_FOR_MANUAL_DECISION","classification":"MIXED_OR_UNRESOLVED","status_reasons":["MIXED_OR_UNRESOLVED"],"checked_commit_sha":"1234567890123456789012345678901234567890","parent_count":1,"child_count":1,"unique_parent_recovered_group_count":0,"unique_child_recovered_group_count":0,"unique_normalized_url_group_count":1,"unique_semantic_parent_group_count":1,"unique_semantic_child_group_count":1,"parents":[{"candidate_number":1,"sheet_row_number":2,"input_state":"EMPTY","host_family":"NONE","path_family":"NONE","allowed_query_key_flags":[],"has_nested_url":False,"decoded_layer_count":0,"direct_identity_extracted":False,"recovery_method":"NONE","recovered_identity_extracted":False,"declared_media_count":1,"recovered_post_group":"UNRESOLVED","normalized_url_group":"URL_GROUP_1","semantic_parent_group":"SEM_PARENT_GROUP_1","matching_recovered_child_count":0}],"children":[{"child_number":1,"sheet_row_number":2,"input_state":"EMPTY","host_family":"NONE","path_family":"NONE","allowed_query_key_flags":[],"has_nested_url":False,"decoded_layer_count":0,"direct_identity_extracted":False,"recovery_method":"NONE","recovered_identity_extracted":False,"media_index":0,"media_type":"unknown","recovered_post_group":"UNRESOLVED","normalized_url_group":"URL_GROUP_1","child_id_group":"CHILD_ID_GROUP_1","semantic_child_group":"SEM_CHILD_GROUP_1"}],"recommended_next_action":"MANUAL_INVESTIGATION","apply_operations":[]}

    def valid_fail_json(self):
        j = self.valid_ready_json()
        j["overall_status"] = "FAIL"
        return j

    def run_renderer_fail(self, j, exit_code):
        import tempfile, json, subprocess
        with tempfile.NamedTemporaryFile("w") as fj, tempfile.NamedTemporaryFile("w") as fs:
            json.dump(j, fj)
            fj.flush()
            p = subprocess.run(["python3", "scripts/render_wp3c4_url_shape_summary.py", "--json-input", fj.name, "--summary-output", fs.name, "--exit-code", str(exit_code)], capture_output=True, text=True)
            with open(fs.name) as f2:
                summary = f2.read()
            return summary, p.stderr

    def run_renderer(self, j, exit_code):
        import tempfile, json, subprocess
        with tempfile.NamedTemporaryFile("w") as fj, tempfile.NamedTemporaryFile("w") as fs:
            json.dump(j, fj)
            fj.flush()
            p = subprocess.run(["python3", "scripts/render_wp3c4_url_shape_summary.py", "--json-input", fj.name, "--summary-output", fs.name, "--exit-code", str(exit_code)], capture_output=True, text=True)
            if p.returncode != exit_code:
                raise RuntimeError(p.stderr)
            with open(fs.name) as f2:
                return f2.read()

    def test_renderer_ready_exit_0(self):
        j = self.valid_ready_json()
        out = self.run_renderer(j, 0)
        self.assertIn("READY_FOR_MANUAL_DECISION", out)
        
    def test_renderer_fail_exit_1(self):
        j = self.valid_fail_json()
        out, err = self.run_renderer_fail(j, 1)
        self.assertIn("FAIL", out)
        
    def test_renderer_fail_exit_0_rejected(self):
        j = self.valid_fail_json()
        out, err = self.run_renderer_fail(j, 0)
        self.assertIn("WP3-C4 summary renderer failed: ValueError", err)
        
    def test_renderer_ready_exit_1_rejected(self):
        j = self.valid_ready_json()
        out, err = self.run_renderer_fail(j, 1)
        self.assertIn("WP3-C4 summary renderer failed: ValueError", err)
        
    def test_renderer_mode_invalid(self):
        j = self.valid_ready_json()
        j["mode"] = "INVALID"
        out, err = self.run_renderer_fail(j, 0)
        self.assertIn("ValueError", err)
        
    def test_renderer_sha_invalid(self):
        j = self.valid_ready_json()
        j["checked_commit_sha"] = "short"
        out, err = self.run_renderer_fail(j, 0)
        self.assertIn("ValueError", err)
        
    def test_renderer_count_type_invalid(self):
        j = self.valid_ready_json()
        j["parent_count"] = "2"
        out, err = self.run_renderer_fail(j, 0)
        self.assertIn("ValueError", err)
        
    def test_renderer_count_mismatch(self):
        j = self.valid_ready_json()
        j["parent_count"] = 99
        out, err = self.run_renderer_fail(j, 0)
        self.assertIn("ValueError", err)
        
    def test_renderer_classification_action_mismatch(self):
        j = self.valid_ready_json()
        j["classification"] = "ACCOUNT_OR_CHANNEL_URLS"
        j["recommended_next_action"] = "MANUAL_INVESTIGATION"
        out, err = self.run_renderer_fail(j, 0)
        self.assertIn("ValueError", err)
        
    def test_renderer_parent_missing_key(self):
        j = self.valid_ready_json()
        del j["parents"][0]["host_family"]
        out, err = self.run_renderer_fail(j, 0)
        self.assertIn("ValueError", err)
        
    def test_renderer_child_missing_key(self):
        j = self.valid_ready_json()
        del j["children"][0]["host_family"]
        out, err = self.run_renderer_fail(j, 0)
        self.assertIn("ValueError", err)
        
    def test_renderer_group_64_hex(self):
        j = self.valid_ready_json()
        j["parents"][0]["normalized_url_group"] = "a" * 64
        out, err = self.run_renderer_fail(j, 0)
        self.assertIn("ValueError", err)
        
    def test_renderer_group_url(self):
        j = self.valid_ready_json()
        j["parents"][0]["normalized_url_group"] = "https://example.com"
        out, err = self.run_renderer_fail(j, 0)
        self.assertIn("ValueError", err)
        
    def test_renderer_status_reason_url(self):
        j = self.valid_ready_json()
        j["status_reasons"] = ["https://example.com"]
        out, err = self.run_renderer_fail(j, 0)
        self.assertIn("ValueError", err)
        
    def test_renderer_apply_operations_not_empty(self):
        j = self.valid_ready_json()
        j["apply_operations"] = ["something"]
        out, err = self.run_renderer_fail(j, 0)
        self.assertIn("ValueError", err)
        
    def test_renderer_invalid_input_summary_unchanged(self):
        j = self.valid_ready_json()
        del j["mode"]
        import tempfile, json, subprocess
        with tempfile.NamedTemporaryFile("w") as fj, tempfile.NamedTemporaryFile("w") as fs:
            json.dump(j, fj)
            fj.flush()
            fs.write("ORIGINAL_SUMMARY")
            fs.flush()
            p = subprocess.run(["python3", "scripts/render_wp3c4_url_shape_summary.py", "--json-input", fj.name, "--summary-output", fs.name, "--exit-code", "0"], capture_output=True, text=True)
            self.assertEqual(p.returncode, 1)
            with open(fs.name) as f2:
                self.assertEqual(f2.read(), "ORIGINAL_SUMMARY")
                
    def test_renderer_stderr_fixed_format(self):
        j = self.valid_ready_json()
        del j["mode"]
        import tempfile, json, subprocess
        with tempfile.NamedTemporaryFile("w") as fj, tempfile.NamedTemporaryFile("w") as fs:
            json.dump(j, fj)
            fj.flush()
            p = subprocess.run(["python3", "scripts/render_wp3c4_url_shape_summary.py", "--json-input", fj.name, "--summary-output", fs.name, "--exit-code", "0"], capture_output=True, text=True)
            self.assertEqual(p.stderr.strip(), "WP3-C4 summary renderer failed: ValueError")

    def test_renderer_subprocess(self):
        with tempfile.NamedTemporaryFile("w+", delete=False) as temp_json:
            json.dump({
                "schema_version": 1,
                "mode": "READ_ONLY_SAFE_URL_SHAPE_DIAGNOSTICS",
                "overall_status": "READY_FOR_MANUAL_DECISION",
                "classification": "MIXED_OR_UNRESOLVED",
                "status_reasons": ["MIXED_OR_UNRESOLVED"],
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
