import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from inspect_wp3c3_source_identity_collision import inspect_wp3c3, TARGET_SOURCE_POST_ID
from render_wp3c3_identity_summary import validate_contract, render_markdown

class TestWP3C3Inspection(unittest.TestCase):
    def test_same_post_reingested(self):
        # 3 identical parents and 3 identical children (except physical row)
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
            (4, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
        ]
        children = [
            (5, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_url": "foo", "source_post_media_id": "c1", "media_index": "0"}),
            (6, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_url": "foo", "source_post_media_id": "c2", "media_index": "0"}),
            (7, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_url": "foo", "source_post_media_id": "c3", "media_index": "0"}),
        ]
        
        rep = inspect_wp3c3(parents, children, "head", "main")
        
        self.assertEqual(rep["classification"], "SAME_POST_REINGESTED")
        self.assertEqual(rep["recommended_next_action"], "PLAN_DEDUPLICATION")
        self.assertEqual(rep["apply_operations"], [])
        
        validate_contract(rep, 0)
        
    def test_distinct_posts_collided(self):
        # 3 different urls
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/def", "media_count": "1"}),
            (4, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/ghi", "media_count": "1"}),
        ]
        children = [
            (5, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc"}),
            (6, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/def"}),
            (7, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/ghi"}),
        ]
        
        rep = inspect_wp3c3(parents, children, "head", "main")
        
        self.assertEqual(rep["classification"], "DISTINCT_POSTS_COLLIDED")
        self.assertEqual(rep["recommended_next_action"], "PLAN_REKEY_MIGRATION")
        
    def test_unresolved_identity(self):
        # 1 url cannot be parsed
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
            (4, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://example.com/unparseable", "media_count": "1"}),
        ]
        children = []
        
        rep = inspect_wp3c3(parents, children, "head", "main")
        
        self.assertEqual(rep["classification"], "UNRESOLVED_IDENTITY")
        self.assertEqual(rep["recommended_next_action"], "MANUAL_INVESTIGATION")

    def test_child_identity_mismatch(self):
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
        ]
        children = [
            (5, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/def"}),
        ]
        
        rep = inspect_wp3c3(parents, children, "head", "main")
        self.assertEqual(rep["classification"], "UNRESOLVED_IDENTITY")

    def test_no_raw_urls_in_output(self):
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/SECRETID123", "media_count": "1"}),
        ]
        children = []
        
        rep = inspect_wp3c3(parents, children, "head", "main")
        rep_str = str(rep)
        self.assertNotIn("SECRETID123", rep_str)
        self.assertNotIn("https://", rep_str)

    def test_contract_validation_fails(self):
        with self.assertRaises(ValueError):
            validate_contract({"mode": "wrong"}, 0)
        
        rep = inspect_wp3c3([], [], "head", "main")
        with self.assertRaises(ValueError):
            validate_contract(rep, 1) # fail because overall_status is READY_FOR_MANUAL_DECISION but exit_code=1
            
if __name__ == '__main__':
    unittest.main()
