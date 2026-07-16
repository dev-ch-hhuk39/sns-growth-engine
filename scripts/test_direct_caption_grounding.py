#!/usr/bin/env python3
from __future__ import annotations

from public_post_quality import final_public_post_validator, generate_grounded_reader_facing_post


def main() -> int:
    cases = {
        "night_scout": "時給は高いがノルマと出勤の負担を確認したい。source_url=private",
        "liver_manager": "初見がコメントに参加しやすい導入と継続の工夫。transcript=private",
    }
    checks: list[tuple[str, bool]] = []
    for account_id, signal in cases.items():
        output = generate_grounded_reader_facing_post(
            account_id,
            private_signal=signal,
            media_metadata={"media_type": "video", "duration_seconds": 22},
            slot_theme="production_grounding_test",
            recent_posts=["過去の別テーマ投稿です。"],
            index=3,
        )
        checks.extend([
            (f"{account_id}:validator", final_public_post_validator(output, account_id)["status"] == "PASS"),
            (f"{account_id}:grounding", bool(output.get("grounding_summary", {}).get("concepts"))),
            (f"{account_id}:transform", bool(output.get("transformation_summary"))),
            (f"{account_id}:similarity", float(output.get("similarity_score", 1)) <= 0.45),
            (f"{account_id}:no raw", signal not in output["public_post_text"]),
        ])
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
