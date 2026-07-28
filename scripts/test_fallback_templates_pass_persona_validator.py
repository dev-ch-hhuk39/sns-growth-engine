#!/usr/bin/env python3
"""Emergency fallback templates remain validator-safe for both accounts."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from public_post_quality import final_public_post_validator, generate_reader_facing_post

for account_id in ("night_scout", "liver_manager"):
    for index in range(1, 26):
        output = generate_reader_facing_post(account_id, index=index)
        result = final_public_post_validator(output["public_post_text"], account_id)
        assert result["status"] == "PASS", (account_id, index, result["blocked_reasons"])

print("PASS test_fallback_templates_pass_persona_validator.py")
