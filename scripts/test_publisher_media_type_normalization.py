#!/usr/bin/env python3
from media_post_validator import publisher_media_type

assert publisher_media_type("direct_image") == "IMAGE"
assert publisher_media_type("direct_video") == "VIDEO"
assert publisher_media_type("approved_source_clip") == "VIDEO"
assert publisher_media_type("direct_carousel", ["one", "two"]) == "CAROUSEL"
print("PASS test_publisher_media_type_normalization.py")
