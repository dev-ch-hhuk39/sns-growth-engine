#!/usr/bin/env python3
from public_post_quality import final_public_post_validator, generate_reader_facing_post


def main() -> int:
    text = generate_reader_facing_post("liver_manager")["public_post_text"]
    result = final_public_post_validator(text, "liver_manager")
    ok = result["status"] == "PASS"
    print(f"  {'PASS' if ok else 'FAIL'} good liver_manager post allowed")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
