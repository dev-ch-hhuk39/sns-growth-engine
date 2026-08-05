#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "auto_approve_queue",
    ROOT / "scripts/auto_approve_queue.py",
)
if spec is None or spec.loader is None:
    raise RuntimeError("auto_approve_queue_spec_unavailable")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

from hybrid_ai_gate import GATE_SCHEMA_VERSION, hybrid_ai_input_hash  # noqa: E402
from hybrid_ai_source_context import hybrid_ai_source_context_hash  # noqa: E402


def add_mock_gate(queue: dict[str, str], public_post_text: str) -> None:
    queue["public_post_text"] = public_post_text
    queue["generation_policy_json"] = json.dumps(
        {
            "hybrid_ai_gate": {
                "schema_version": GATE_SCHEMA_VERSION,
                "status": "PASS",
                "input_hash": hybrid_ai_input_hash(queue),
                "source_context_hash": hybrid_ai_source_context_hash({}),
                "route": "new_text_generation",
            }
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def main() -> int:
    rules = mod.rules_for_account(mod.load_rules(), "night_scout")
    derivative = {
        "text": (
            "夜職で店を選ぶときは、時給だけで決めると続けにくくなることがあります。\n\n"
            "客層や出勤ペース、担当への相談のしやすさまで確認して、"
            "自分が無理なく続けられる環境かを整理することが大切です。"
        )
    }
    queue = {
        "queue_id": "q1",
        "account_id": "night_scout",
        "platform": "threads",
        "status": "WAITING_REVIEW",
        "generation_mode": "reference_score_to_threads",
        "media_reuse_risk": "",
    }
    draft = {"source_refs": "ref1", "media_strategy": "none"}

    missing = mod.evaluate_item(
        queue=queue,
        draft=draft,
        derivative=derivative,
        scores_by_ref={"ref1": {"recommended_use": "REFERENCE_ONLY"}},
        existing_texts=[],
        rules=rules,
        source_context={},
    )
    add_mock_gate(queue, derivative["text"])
    gated = mod.evaluate_item(
        queue=queue,
        draft=draft,
        derivative=derivative,
        scores_by_ref={"ref1": {"recommended_use": "REFERENCE_ONLY"}},
        existing_texts=[],
        rules=rules,
        source_context={},
    )

    checks = [
        (
            "ungated candidate blocked",
            missing["status"] == "REJECTED"
            and "hybrid_ai_gate_missing" in missing["reasons"],
        ),
        ("gated dry-run candidate approvable", gated["status"] == "APPROVABLE"),
        (
            "scores present",
            gated["quality_score"] >= 75 and gated["safety_score"] >= 90,
        ),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
