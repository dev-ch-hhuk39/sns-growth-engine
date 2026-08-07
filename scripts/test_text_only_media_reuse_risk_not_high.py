from unittest.mock import patch

import generate_threads_ideas_from_references as generator
from autonomous_recovery_test_utils import test_text_only_media_reuse_risk_not_high
from reference_rewrite_ci_stub import fake_reference_rewrite

with patch.object(generator, "rewrite_reference_post", side_effect=fake_reference_rewrite):
    test_text_only_media_reuse_risk_not_high()
print("PASS test_text_only_media_reuse_risk_not_high.py")
