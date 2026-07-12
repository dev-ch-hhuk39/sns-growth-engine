#!/usr/bin/env python3
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_media_production_pipeline import build_plan  # noqa: E402
from run_media_production_pipeline import REQUIRED_ENV  # noqa: E402


class EmptyClient:
    def _ensure_tab(self, *_args, **_kwargs):
        return None

    def _ws(self, _logical):
        class WS:
            def get_all_records(self):
                return []

        return WS()


def main() -> int:
    for name in REQUIRED_ENV:
        os.environ[name] = "true"
    plan = build_plan(apply=True, confirm=True, client=EmptyClient())
    checks = [
        ("status is NO_POST", plan["status"] == "NO_POST"),
        ("reason is visible", "no_eligible_media_candidate" in plan["blocked_reasons"]),
        ("no external actions", not plan["would_download"] and not plan["would_cut"] and not plan["would_upload"] and not plan["would_post_video"]),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
