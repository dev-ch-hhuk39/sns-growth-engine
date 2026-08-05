#!/usr/bin/env python3
from activated_autopost_test_utils import MEDIA_PUBLISH_WORKFLOWS, assert_media_publish_contract
assert_media_publish_contract(MEDIA_PUBLISH_WORKFLOWS["night_scout_direct"], "ns_1800_direct_media")
assert_media_publish_contract(MEDIA_PUBLISH_WORKFLOWS["night_scout_clip"], "ns_2100_clip_media")
assert_media_publish_contract(MEDIA_PUBLISH_WORKFLOWS["liver_manager_direct"], "lm_1600_direct_media")
assert_media_publish_contract(MEDIA_PUBLISH_WORKFLOWS["liver_manager_clip"], "lm_1800_clip_media")
print("PASS test_media_slots_no_text_fallback_final.py")
