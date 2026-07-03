#!/usr/bin/env python3
from public_post_quality import INTERNAL_LEAK_TERMS, final_public_post_validator, generate_reader_facing_post


def main() -> int:
    texts = [
        generate_reader_facing_post("night_scout")["public_post_text"],
        generate_reader_facing_post("liver_manager")["public_post_text"],
    ]
    ok = all(final_public_post_validator(t, acct)["status"] == "PASS" for t, acct in zip(texts, ["night_scout", "liver_manager"]))
    ok = ok and not any(term.lower() in "\n".join(texts).lower() for term in INTERNAL_LEAK_TERMS)
    print(f"  {'PASS' if ok else 'FAIL'} internal terms absent from generated public text")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
