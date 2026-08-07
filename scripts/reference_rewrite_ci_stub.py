"""Deterministic no-network stub used only by legacy repository contract tests.

Production reference generation must use generation.reference_source_rewriter.
This helper exists so legacy reader-facing/queue tests do not require a Gemini
secret or network call while still exercising their original contract.
"""
from __future__ import annotations

import re
from typing import Any

from public_post_quality import generate_reader_facing_post, reader_facing_template_count


def fake_reference_rewrite(**kwargs: Any) -> dict[str, Any]:
    account_id = str(kwargs.get("account_id") or "")
    source = dict(kwargs.get("source") or {})
    identity = str(
        source.get("post_id")
        or source.get("raw_item_id")
        or source.get("source_id")
        or source.get("text")
        or "1"
    )
    match = re.search(r"(\d+)(?!.*\d)", identity)
    ordinal = int(match.group(1)) if match else max(1, sum(ord(ch) for ch in identity))
    count = max(1, reader_facing_template_count(account_id))
    template_index = ((ordinal - 1) % count) + 1
    body = str(generate_reader_facing_post(account_id, template_index)["public_post_text"])
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", body) if part.strip()]
    semantic = {"pass": True, "reason": "explicit deterministic no-network test stub"}
    return {
        "public_post_text": body,
        "generation_model": "test-no-network",
        "generation_strategy": "test_source_grounded_stub",
        "feature_schema_version": "test_source_grounded_stub_v1",
        "generation_policy": {
            "policy": "test_source_grounded_stub",
            "semantic_fidelity_required": True,
            "unrelated_fallback_allowed": False,
            "test_only": True,
        },
        "grounding_summary": {
            "generation_strategy": "test_source_grounded_stub",
            "structure_variant": (template_index - 1) % 6,
            "quality_topic": "",
            "semantic_fidelity": semantic,
        },
        "post_design": {
            "hook_text": paragraphs[0] if paragraphs else body[:80],
            "body_text": "\n\n".join(paragraphs[1:-1]) if len(paragraphs) > 2 else "",
            "closing_text": paragraphs[-1] if len(paragraphs) > 1 else "",
            "cta_intent": "none",
            "key_claims": [],
        },
        "semantic_fidelity": semantic,
    }
