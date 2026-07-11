#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from publishers.threads_publisher import ThreadsPublisher


secret = "never-print-this-access-token"
text = "配信を始めたばかりなら、まずは初見の人が入りやすい挨拶を決めておく。毎回同じ入り口があるだけで、話し始めの迷いは減らせる。"
with patch.dict(os.environ, {
    "PUBLISH_ENABLED": "true",
    "ALLOW_REAL_THREADS_POST": "true",
}, clear=False), patch(
    "publishers.threads_publisher._get_credentials",
    return_value=(secret, "user-id"),
), patch(
    "publishers.threads_publisher._create_container",
    side_effect=RuntimeError(f"request failed https://example.invalid?access_token={secret}"),
):
    result = ThreadsPublisher().publish(
        text,
        account={"account_id": "liver_manager"},
        derivative={},
        queue_item={"queue_id": "q_test"},
        dry_run=False,
    )

checks = [
    result.success is False,
    "RuntimeError" in result.message,
    secret not in result.message,
    "access_token" not in result.message,
]
print(f"PASS: {sum(checks)} / FAIL: {len(checks)-sum(checks)}")
raise SystemExit(0 if all(checks) else 1)
