#!/usr/bin/env python3
"""Private reference/transcript signals must yield safe public-only text."""
from __future__ import annotations

from public_post_quality import final_public_post_validator, generate_grounded_reader_facing_post


def main() -> int:
    samples = {
        "night_scout": "時給より客層とノルマが大事。source_id=private transcript",
        "liver_manager": "初見がコメントしやすい空気を作る。source_url private transcript",
    }
    checks = []
    for account, signal in samples.items():
        output = generate_grounded_reader_facing_post(account, private_signal=signal)
        validation = final_public_post_validator(output, account)
        checks.extend([
            (f"{account} validator passes", validation["status"] == "PASS"),
            (f"{account} public text differs from private signal", output["public_post_text"] not in signal),
            (f"{account} internal text stays structured", bool(output["internal_analysis"]) and bool(output["safety_notes"])),
            (f"{account} grounding summary exists", bool(output.get("grounding_summary", {}).get("concepts"))),
            (f"{account} transformation summary exists", bool(output.get("transformation_summary"))),
            (f"{account} source similarity is safe", float(output.get("similarity_score", 1)) <= 0.45),
            (f"{account} validator result persisted", output.get("validator_result") == "PASS"),
        ])
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
