#!/usr/bin/env python3
from activated_autopost_test_utils import MEDIA_PREP_WORKFLOWS, assert_media_preparation_contract
assert_media_preparation_contract(MEDIA_PREP_WORKFLOWS["liver_manager_clip_prepare"], "lm_1800_clip_media")
print("PASS test_media_production_workflow.py")
