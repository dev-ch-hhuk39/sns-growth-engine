import os
import sys
import unittest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.url_shape_diagnostics import parse_url_shape, normalize_url_for_safe_grouping, normalize_media_url_for_fingerprint

class TestUrlShapeDiagnostics(unittest.TestCase):
    def test_direct_identities(self):
        shapes = [
            parse_url_shape("https://www.youtube.com/watch?v=12345678901"),
            parse_url_shape("https://www.threads.net/@user/post/1234567"),
            parse_url_shape("https://www.tiktok.com/@user/video/1234567890123456789")
        ]
        for s in shapes:
            self.assertTrue(s.direct_identity_extracted)
            self.assertTrue(bool(s.recovered_stable_post_id))
            self.assertEqual(s.recovery_method, "DIRECT")

    def test_youtube_paths(self):
        self.assertEqual(parse_url_shape("https://youtube.com/watch?v=1").path_family, "WATCH")
        self.assertEqual(parse_url_shape("https://youtube.com/shorts/1").path_family, "SHORTS")
        self.assertEqual(parse_url_shape("https://youtube.com/live/1").path_family, "LIVE")
        self.assertEqual(parse_url_shape("https://youtube.com/embed/1").path_family, "EMBED")
        self.assertEqual(parse_url_shape("https://youtube.com/channel/1").path_family, "CHANNEL")
        self.assertEqual(parse_url_shape("https://youtube.com/user/1").path_family, "USER")
        self.assertEqual(parse_url_shape("https://youtube.com/@handle").path_family, "HANDLE")
        self.assertEqual(parse_url_shape("https://youtube.com/playlist?list=1").path_family, "PLAYLIST")
        self.assertEqual(parse_url_shape("https://youtu.be/1").host_family, "YOUTU_BE")

    def test_threads_paths(self):
        self.assertEqual(parse_url_shape("https://threads.net/@user/post/1").path_family, "THREADS_POST")
        self.assertEqual(parse_url_shape("https://threads.net/@user").path_family, "HANDLE")
        
    def test_tiktok_paths(self):
        self.assertEqual(parse_url_shape("https://tiktok.com/@user/video/1").path_family, "TIKTOK_VIDEO")
        self.assertEqual(parse_url_shape("https://tiktok.com/@user").path_family, "HANDLE")

    def test_google_redirect(self):
        self.assertEqual(parse_url_shape("https://google.com/url?q=1").path_family, "REDIRECT")
        self.assertEqual(parse_url_shape("https://google.com/url?q=1").host_family, "GOOGLE_REDIRECT")
        self.assertEqual(parse_url_shape("https://fake.google.com/url?q=1").host_family, "OTHER")
        
    def test_percent_encoded(self):
        s = parse_url_shape("https://google.com/url?q=https%3A%2F%2Fyoutube.com%2Fwatch%3Fv%3D12345678901")
        self.assertTrue(s.has_nested_url)
        self.assertTrue(bool(s.recovered_stable_post_id))
        self.assertEqual(s.recovery_method, "NESTED_QUERY_URL")
        
    def test_double_encoded(self):
        s = parse_url_shape("https%3A%2F%2Fyoutube.com%2Fwatch%3Fv%3D12345678901")
        self.assertTrue(bool(s.recovered_stable_post_id))
        self.assertEqual(s.recovery_method, "PERCENT_DECODED_URL")
        self.assertEqual(s.decoded_layer_count, 1)
        
    def test_malformed_empty(self):
        self.assertEqual(parse_url_shape("").input_state, "EMPTY")
        self.assertEqual(parse_url_shape("not a url").input_state, "MALFORMED")
        self.assertEqual(parse_url_shape("youtube.com/watch?v=12345678901").input_state, "SCHEME_MISSING")

    def test_unknown_host(self):
        self.assertEqual(parse_url_shape("https://example.com").host_family, "OTHER")

    def test_fake_hosts(self):
        self.assertEqual(parse_url_shape("https://fakeyoutube.com").host_family, "OTHER")
        self.assertEqual(parse_url_shape("https://fakethreads.net").host_family, "OTHER")
        self.assertEqual(parse_url_shape("https://faketiktok.com").host_family, "OTHER")

    def test_unknown_query_ignored(self):
        s = parse_url_shape("https://example.com/?unknown=https://youtube.com/watch?v=12345678901")
        self.assertFalse(s.has_nested_url)
        self.assertFalse(bool(s.recovered_stable_post_id))

    def test_normalization_no_query_value(self):
        h1 = normalize_url_for_safe_grouping("https://youtube.com/watch?v=1&utm_source=a")
        h2 = normalize_url_for_safe_grouping("https://youtube.com/watch?v=1&utm_source=b")
        self.assertEqual(h1, h2)
        
    def test_normalization_media_url(self):
        h1 = normalize_media_url_for_fingerprint("https://cdn.example.com/video.mp4?token=123")
        h2 = normalize_media_url_for_fingerprint("https://cdn.example.com/video.mp4?token=456")
        self.assertEqual(h1, h2)
        
    def test_normalization_no_hash(self):
        self.assertNotIn("http", normalize_url_for_safe_grouping("https://example.com"))
        
    def test_normalization_order_independent(self):
        h1 = normalize_url_for_safe_grouping("https://youtube.com/watch?v=1&list=2")
        h2 = normalize_url_for_safe_grouping("https://youtube.com/watch?list=2&v=1")
        self.assertEqual(h1, h2)
        
    def test_token_excluded(self):
        h1 = normalize_url_for_safe_grouping("https://example.com/?token=123")
        h2 = normalize_url_for_safe_grouping("https://example.com/?token=456")
        self.assertEqual(h1, h2)

if __name__ == "__main__":
    unittest.main()
