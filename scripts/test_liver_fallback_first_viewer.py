#!/usr/bin/env python3
"""The first-viewer fallback stays valid regardless of date-selected framing."""
from public_post_quality import (
    PRODUCTION_COMPONENTS, PRODUCTION_CLOSINGS, apply_account_voice,
    final_public_post_validator,
)

component = PRODUCTION_COMPONENTS["liver_manager"]["first_viewer"]
# This body previously lacked a logical explanation and enough audience
# context; date-dependent selection could produce a blocked recovery draft.
body = component["bodies"][1]
for hook in component["hooks"]:
    for closing in PRODUCTION_CLOSINGS["liver_manager"]["first_viewer"]:
        text = apply_account_voice(f"{hook}\n\n{body}\n\n{closing}", "liver_manager")
        result = final_public_post_validator(text, "liver_manager")
        assert result["status"] == "PASS", result
        assert "私" in text and "僕" not in text and "俺" not in text
print("PASS liver first-viewer fallback: 9 framing combinations")
