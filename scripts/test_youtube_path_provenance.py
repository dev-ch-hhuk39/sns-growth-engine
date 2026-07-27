#!/usr/bin/env python3
import os
import sys
import unittest

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

class TestYouTubePathProvenance(unittest.TestCase):
    def test_handle_root(self):
        shape = analyse_youtube_url("https://youtube.com/@somehandle")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_HANDLE_ROOT)
        self.assertEqual(shape.tab_kind, TabKind.NONE)
        self.assertEqual(shape.post_kind, PostKind.NONE)
        
    def test_handle_tab(self):
        shape = analyse_youtube_url("https://youtube.com/@somehandle/videos")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_HANDLE_TAB)
        self.assertEqual(shape.tab_kind, TabKind.VIDEOS)
        
    def test_channel_root(self):
        shape = analyse_youtube_url("https://youtube.com/channel/UC123")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_CHANNEL_ROOT)
        
    def test_post_watch(self):
        shape = analyse_youtube_url("https://youtube.com/watch?v=123")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_POST_URL)
        self.assertEqual(shape.post_kind, PostKind.WATCH)
        self.assertTrue(shape.post_identity_extracted)
        
    def test_post_shorts(self):
        shape = analyse_youtube_url("https://youtube.com/shorts/123")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_POST_URL)
        self.assertEqual(shape.post_kind, PostKind.SHORTS)
        self.assertTrue(shape.post_identity_extracted)
        
    def test_post_youtu_be(self):
        shape = analyse_youtube_url("https://youtu.be/123")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_POST_URL)
        self.assertEqual(shape.post_kind, PostKind.YOUTU_BE)
        self.assertTrue(shape.post_identity_extracted)

    def test_shape_to_safe_dict(self):
        shape = analyse_youtube_url("https://youtube.com/watch?v=123")
        d = shape_to_safe_dict(shape)
        self.assertEqual(d["host_family"], "YOUTUBE")
        self.assertEqual(d["path_shape"], "YOUTUBE_POST_URL")
        self.assertEqual(d["tab_kind"], "NONE")
        self.assertEqual(d["post_kind"], "WATCH")
        self.assertTrue(d["post_identity_extracted"])

if __name__ == "__main__":
    unittest.main()
