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

import scripts.inspect_wp3c5_youtube_path_provenance as inspector
from scripts.inspect_wp3c5_youtube_path_provenance import main

class TestWP3C5YouTubePathProvenance(unittest.TestCase):
    def setUp(self):
        # We don't patch sys.exit globally to avoid breaking test runner
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

if __name__ == "__main__":
    unittest.main()
