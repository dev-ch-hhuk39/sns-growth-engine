import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from source_post_identity import extract_source_post_identity

class TestSourcePostIdentity(unittest.TestCase):
    def test_youtube_watch(self):
        r = extract_source_post_identity("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(r.stable_post_id, "dQw4w9WgXcQ")
        self.assertEqual(r.platform, "youtube")
        
        r2 = extract_source_post_identity("https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=5s")
        self.assertEqual(r2.stable_post_id, "dQw4w9WgXcQ")
        
    def test_youtube_shorts(self):
        r = extract_source_post_identity("https://www.youtube.com/shorts/dQw4w9WgXcQ")
        self.assertEqual(r.stable_post_id, "dQw4w9WgXcQ")
        self.assertEqual(r.platform, "youtube")

    def test_youtube_live(self):
        r = extract_source_post_identity("https://www.youtube.com/live/dQw4w9WgXcQ?feature=share")
        self.assertEqual(r.stable_post_id, "dQw4w9WgXcQ")
        
    def test_youtube_youtu_be(self):
        r = extract_source_post_identity("https://youtu.be/dQw4w9WgXcQ?t=1")
        self.assertEqual(r.stable_post_id, "dQw4w9WgXcQ")
        
    def test_youtube_invalid(self):
        r = extract_source_post_identity("https://www.youtube.com/@channel")
        self.assertEqual(r.confidence, "NONE")
        r = extract_source_post_identity("https://www.youtube.com/playlist?list=XYZ")
        self.assertEqual(r.confidence, "NONE")

    def test_threads(self):
        r = extract_source_post_identity("https://www.threads.net/@user/post/Cw123456789")
        self.assertEqual(r.stable_post_id, "Cw123456789")
        self.assertEqual(r.platform, "threads")

        r2 = extract_source_post_identity("https://threads.com/@user/post/Cw123456789/?token=abc")
        self.assertEqual(r2.stable_post_id, "Cw123456789")
        self.assertEqual(r2.platform, "threads")

    def test_tiktok(self):
        r = extract_source_post_identity("https://www.tiktok.com/@user/video/1234567890123456789")
        self.assertEqual(r.stable_post_id, "1234567890123456789")
        self.assertEqual(r.platform, "tiktok")
        
    def test_tiktok_short(self):
        r = extract_source_post_identity("https://vm.tiktok.com/ZM1234567/")
        self.assertEqual(r.confidence, "NONE")
        r2 = extract_source_post_identity("https://vt.tiktok.com/ZS1234567/")
        self.assertEqual(r2.confidence, "NONE")

    def test_unknown(self):
        r = extract_source_post_identity("https://example.com/video")
        self.assertEqual(r.confidence, "NONE")

if __name__ == '__main__':
    unittest.main()
