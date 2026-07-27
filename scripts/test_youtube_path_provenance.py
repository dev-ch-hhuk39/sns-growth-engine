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
        
    def test_handle_videos_tab(self):
        shape = analyse_youtube_url("https://youtube.com/@somehandle/videos")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_HANDLE_TAB)
        self.assertEqual(shape.tab_kind, TabKind.VIDEOS)
        
    def test_handle_shorts_tab(self):
        shape = analyse_youtube_url("https://youtube.com/@somehandle/shorts")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_HANDLE_TAB)
        self.assertEqual(shape.tab_kind, TabKind.SHORTS)

    def test_handle_streams_tab(self):
        shape = analyse_youtube_url("https://youtube.com/@somehandle/streams")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_HANDLE_TAB)
        self.assertEqual(shape.tab_kind, TabKind.STREAMS)

    def test_channel_root(self):
        shape = analyse_youtube_url("https://youtube.com/channel/UC123")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_CHANNEL_ROOT)

    def test_channel_videos_tab(self):
        shape = analyse_youtube_url("https://youtube.com/channel/UC123/videos")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_CHANNEL_TAB)
        self.assertEqual(shape.tab_kind, TabKind.VIDEOS)

    def test_user_root(self):
        shape = analyse_youtube_url("https://youtube.com/user/someone")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_USER_ROOT)

    def test_user_tab(self):
        shape = analyse_youtube_url("https://youtube.com/user/someone/about")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_USER_TAB)
        self.assertEqual(shape.tab_kind, TabKind.ABOUT)

    def test_custom_root(self):
        shape = analyse_youtube_url("https://youtube.com/c/someone")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_CUSTOM_ROOT)

    def test_custom_tab(self):
        shape = analyse_youtube_url("https://youtube.com/c/someone/community")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_CUSTOM_TAB)
        self.assertEqual(shape.tab_kind, TabKind.COMMUNITY)
        
    def test_watch_post(self):
        shape = analyse_youtube_url("https://youtube.com/watch?v=123")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_POST_URL)
        self.assertEqual(shape.post_kind, PostKind.WATCH)
        self.assertTrue(shape.post_identity_extracted)

    def test_watch_without_v(self):
        shape = analyse_youtube_url("https://youtube.com/watch?list=123")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_POST_URL)
        self.assertEqual(shape.post_kind, PostKind.WATCH)
        self.assertFalse(shape.post_identity_extracted)
        
    def test_shorts_post(self):
        shape = analyse_youtube_url("https://youtube.com/shorts/123")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_POST_URL)
        self.assertEqual(shape.post_kind, PostKind.SHORTS)
        self.assertTrue(shape.post_identity_extracted)

    def test_live_post(self):
        shape = analyse_youtube_url("https://youtube.com/live/123")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_POST_URL)
        self.assertEqual(shape.post_kind, PostKind.LIVE)
        self.assertTrue(shape.post_identity_extracted)
        
    def test_youtu_be_post(self):
        shape = analyse_youtube_url("https://youtu.be/123")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_POST_URL)
        self.assertEqual(shape.post_kind, PostKind.YOUTU_BE)
        self.assertTrue(shape.post_identity_extracted)

    def test_youtu_be_root_without_id(self):
        shape = analyse_youtube_url("https://youtu.be/")
        self.assertEqual(shape.path_shape, PathShape.YOUTUBE_POST_URL)
        self.assertEqual(shape.post_kind, PostKind.YOUTU_BE)
        self.assertFalse(shape.post_identity_extracted)

    def test_malformed(self):
        shape = analyse_youtube_url("not_a_url")
        self.assertEqual(shape.input_state, "MALFORMED")

    def test_empty(self):
        shape = analyse_youtube_url("")
        self.assertEqual(shape.input_state, "EMPTY")

    def test_non_youtube(self):
        shape = analyse_youtube_url("https://example.com/watch")
        self.assertEqual(shape.host_family, "NON_YOUTUBE")
        self.assertEqual(shape.path_shape, PathShape.NON_YOUTUBE)

    def test_relative_path(self):
        shape = analyse_youtube_url("/watch?v=123")
        self.assertEqual(shape.input_state, "RELATIVE")

    def test_shape_to_safe_dict_no_raw_values(self):
        shape = analyse_youtube_url("https://youtube.com/watch?v=123&t=10s#frag")
        d = shape_to_safe_dict(shape)
        
        # Check safe dict
        for k, v in d.items():
            if type(v) is str:
                self.assertNotIn("123", v)
                self.assertNotIn("frag", v)
                self.assertNotIn("youtube.com", v)
            if type(v) is list:
                self.assertNotIn("123", v)
                self.assertNotIn("frag", v)

if __name__ == "__main__":
    unittest.main()
