#!/usr/bin/env python3
from unittest.mock import patch

import generate_threads_ideas_from_references as generator
from public_post_quality import final_public_post_validator
from reference_rewrite_ci_stub import fake_reference_rewrite


def main() -> int:
    with patch.object(generator, "rewrite_reference_post", side_effect=fake_reference_rewrite):
        body = generator.build_thread_body("liver_manager", {"text": "参考テーマ"}, {}, 1)
    result = final_public_post_validator(body, "liver_manager")
    ok = result["status"] == "PASS" and "今回の切り口" not in body
    print(f"  {'PASS' if ok else 'FAIL'} liver_manager generation reader-facing")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
