#!/usr/bin/env python3
"""ThreadsPublisher の media 配線が dry-run 限定であることを検証する。

保証する性質:
  - dry-run + media_url: 成功・dry_run=True・「DRY_RUN_PLAN_ONLY」を報告（API呼び出しなし）
  - dry-run + media無し: 既存の text-only 挙動のまま（media note なし）
  - real mode + media_url: env フラグが true でも SAFETY_STOP で拒否（実 media 投稿不可）
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from publishers.threads_publisher import ThreadsPublisher

ACCOUNT = {"account_id": "night_scout"}
DERIV = {"derivative_id": "deriv_test"}
QUEUE = {"queue_id": "q_test"}
TEXT = "フックの一文\n\n本文です。"
MEDIA = "https://res.cloudinary.com/demo/image/upload/sample.png"


def main() -> int:
    pub = ThreadsPublisher()
    checks: list[tuple[str, bool]] = []

    # 1) dry-run + media
    r = pub.publish(TEXT, account=ACCOUNT, derivative=DERIV, queue_item=QUEUE,
                    dry_run=True, media_url=MEDIA)
    checks.append(("dryrun+media success", r.success is True))
    checks.append(("dryrun+media dry_run flag", r.dry_run is True))
    checks.append(("dryrun+media no posted_url", r.posted_url is None))
    checks.append(("dryrun+media plan note", "DRY_RUN_PLAN_ONLY" in r.message))
    checks.append(("dryrun+media IMAGE note", "media=IMAGE" in r.message))

    # 2) dry-run + media無し（既存挙動）
    r2 = pub.publish(TEXT, account=ACCOUNT, derivative=DERIV, queue_item=QUEUE, dry_run=True)
    checks.append(("dryrun text-only success", r2.success is True))
    checks.append(("dryrun text-only no media note", "media=IMAGE" not in r2.message))

    # 3) real mode + media: env フラグ true でも拒否（実 media 投稿不可）
    prev_pub = os.environ.get("PUBLISH_ENABLED")
    prev_allow = os.environ.get("ALLOW_REAL_THREADS_POST")
    os.environ["PUBLISH_ENABLED"] = "true"
    os.environ["ALLOW_REAL_THREADS_POST"] = "true"
    try:
        r3 = pub.publish(TEXT, account=ACCOUNT, derivative=DERIV, queue_item=QUEUE,
                         dry_run=False, media_url=MEDIA)
    finally:
        if prev_pub is None:
            os.environ.pop("PUBLISH_ENABLED", None)
        else:
            os.environ["PUBLISH_ENABLED"] = prev_pub
        if prev_allow is None:
            os.environ.pop("ALLOW_REAL_THREADS_POST", None)
        else:
            os.environ["ALLOW_REAL_THREADS_POST"] = prev_allow

    checks.append(("real+media refused", r3.success is False))
    checks.append(("real+media SAFETY_STOP", "SAFETY_STOP" in r3.message))
    checks.append(("real+media mentions media", "media" in r3.message))
    checks.append(("real+media no post_id", r3.external_post_id is None))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
