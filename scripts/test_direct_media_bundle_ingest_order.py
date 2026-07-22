#!/usr/bin/env python3
from ingest_direct_reference_media import source_post_media_bundle


class Worksheet:
    def get_all_records(self):
        return [
            {"source_post_media_id": "m2", "source_post_id": "post_a", "media_index": "2"},
            {"source_post_media_id": "other", "source_post_id": "post_b", "media_index": "0"},
            {"source_post_media_id": "m0", "source_post_id": "post_a", "media_index": "0"},
            {"source_post_media_id": "m1", "source_post_id": "post_a", "media_index": "1"},
        ]


class Client:
    def _ws(self, logical):
        assert logical == "source_post_media"
        return Worksheet()


bundle = source_post_media_bundle(Client(), "post_a")
assert [row["source_post_media_id"] for row in bundle] == ["m0", "m1", "m2"], bundle
print("PASS test_direct_media_bundle_ingest_order.py")
