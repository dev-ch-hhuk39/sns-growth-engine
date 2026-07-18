#!/usr/bin/env python3
"""Every rotating fallback template must be public-safe and account-fitting."""
from public_post_quality import final_public_post_validator, generate_reader_facing_post, reader_facing_template_count


def main() -> int:
    checks: list[tuple[str, bool]] = []
    for account_id in ("night_scout", "liver_manager"):
        count = reader_facing_template_count(account_id)
        validations = [
            final_public_post_validator(generate_reader_facing_post(account_id, index=index)["public_post_text"], account_id)
            for index in range(1, count + 1)
        ]
        checks.append((f"{account_id} has at least ten rotating templates", count >= 10))
        checks.append((f"{account_id} templates all pass final validator", all(item["status"] == "PASS" for item in validations)))
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    failed = [name for name, ok in checks if not ok]
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
