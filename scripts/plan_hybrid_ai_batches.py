#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hybrid_ai_budget import check_capacity
from hybrid_ai_policy import chunk_candidates, estimate_requests


def load_candidates(path: str) -> list[dict[str, Any]]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise RuntimeError("candidate_file_must_be_json_array")
    return [dict(row) for row in value]


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan bounded Gemini hybrid batches")
    parser.add_argument("candidate_json")
    parser.add_argument("--max-requests-per-batch", type=int, default=20)
    args = parser.parse_args()
    candidates = load_candidates(args.candidate_json)
    estimated = estimate_requests(candidates)
    allowed, reasons, snapshot = check_capacity(estimated)
    output = {
        "candidate_count": len(candidates),
        "estimated_total_requests": estimated,
        "budget_allowed_now": allowed,
        "budget_block_reasons": reasons,
        "budget_snapshot": snapshot,
        "batch_count": len(chunk_candidates(candidates, args.max_requests_per_batch)),
        "batches": chunk_candidates(candidates, args.max_requests_per_batch),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
