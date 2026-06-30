#!/usr/bin/env python3
"""Analyze transcript structure for reference-only post generation."""
from __future__ import annotations

import argparse
import json
from typing import Any


def analyze_transcript(text: str) -> dict[str, Any]:
    words = [w for w in text.replace("\n", " ").split(" ") if w]
    hook = " ".join(words[:20])
    return {
        "hook_summary": hook,
        "topic_count": min(5, max(1, len(words) // 40)),
        "topics": ["hook", "problem", "example", "lesson"][: min(4, max(1, len(words) // 20 + 1))],
        "quote_policy": "short excerpts only; transform before use",
        "reference_only": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="analyze video transcript structure")
    parser.add_argument("--text", default="sample hook problem lesson")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps({"status": "PLAN_ONLY", "analysis": analyze_transcript(args.text)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
