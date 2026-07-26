import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from source_post_identity import extract_source_post_identity

class TestSourcePostIdentity(unittest.TestCase):
    def test_youtube_watch(self):
        r = extract_source_post_identity("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(r.stable_post_id, "dQw4w9WgXcQ")
        
        r2 = extract_source_post_identity("https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=5s")
        self.assertEqual(r2.stable_post_id, "dQw4w9WgXcQ")

        r3 = extract_source_post_identity("https://www.youtube.com/watch?v=abc")
        self.assertNotEqual(r.stable_post_id, r3.stable_post_id)

    def test_youtube_shorts(self):
        r = extract_source_post_identity("https://www.youtube.com/shorts/dQw4w9WgXcQ")
        self.assertEqual(r.stable_post_id, "dQw4w9WgXcQ")

    def test_youtube_live(self):
        r = extract_source_post_identity("https://www.youtube.com/live/dQw4w9WgXcQ?feature=share")
        self.assertEqual(r.stable_post_id, "dQw4w9WgXcQ")
        
    def test_youtube_youtu_be(self):
        r = extract_source_post_identity("https://youtu.be/dQw4w9WgXcQ?t=1")
        self.assertEqual(r.stable_post_id, "dQw4w9WgXcQ")
        
        r2 = extract_source_post_identity("https://youtu.be/dQw4w9WgXcQ/extra")
        self.assertEqual(r2.confidence, "NONE")
        
    def test_youtube_invalid(self):
        self.assertEqual(extract_source_post_identity("https://www.youtube.com/@channel").confidence, "NONE")
        self.assertEqual(extract_source_post_identity("https://www.youtube.com/playlist?list=XYZ").confidence, "NONE")
        self.assertEqual(extract_source_post_identity("https://notyoutube.com/watch?v=abc").confidence, "NONE")
        self.assertEqual(extract_source_post_identity("https://youtube.com.evil.example/watch?v=abc").confidence, "NONE")
        self.assertEqual(extract_source_post_identity("https://www.youtube.com/watchlater?v=abc").confidence, "NONE")
        self.assertEqual(extract_source_post_identity("https://www.youtube.com/watch?v=").confidence, "NONE")

    def test_threads(self):
        self.assertEqual(extract_source_post_identity("https://www.threads.net/@user/post/Cw123456789").stable_post_id, "Cw123456789")
        self.assertEqual(extract_source_post_identity("https://threads.com/@user/post/Cw123456789/?token=abc").stable_post_id, "Cw123456789")
        self.assertEqual(extract_source_post_identity("https://threads.com.evil.example/@user/post/abc").confidence, "NONE")

    def test_tiktok(self):
        self.assertEqual(extract_source_post_identity("https://www.tiktok.com/@user/video/1234567890123456789").stable_post_id, "1234567890123456789")
        self.assertEqual(extract_source_post_identity("https://tiktok.com.evil.example/@user/video/123").confidence, "NONE")
        self.assertEqual(extract_source_post_identity("https://vm.tiktok.com/ZM1234567/").confidence, "NONE")
        self.assertEqual(extract_source_post_identity("https://vt.tiktok.com/ZS1234567/").confidence, "NONE")

    def test_unknown(self):
        self.assertEqual(extract_source_post_identity("https://example.com/video").confidence, "NONE")

if __name__ == '__main__':
    unittest.main()
