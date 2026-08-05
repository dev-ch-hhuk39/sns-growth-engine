#!/usr/bin/env python3
from activated_autopost_test_utils import MEDIA_PREP_WORKFLOWS, assert_media_preparation_contract
assert_media_preparation_contract(MEDIA_PREP_WORKFLOWS["night_scout_clip_prepare"], "ns_2100_clip_media")
print("PASS test_media_production_night_scout_workflow.py")
