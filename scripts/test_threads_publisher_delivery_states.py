#!/usr/bin/env python3
"""Container lifecycle states must prevent ambiguous publish retries."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from publishers.threads_publisher import ThreadsPublisher

os.environ["PUBLISH_ENABLED"] = "true"
os.environ["ALLOW_REAL_THREADS_POST"] = "true"

publisher = ThreadsPublisher()
kwargs = {"account": {"account_id": "night_scout"}, "derivative": {}, "queue_item": {"queue_id": "q1"}, "dry_run": False}
with patch("publishers.threads_publisher._get_credentials", return_value=("token", "user")), patch("publishers.threads_publisher._create_container", return_value="container-1"), patch("publishers.threads_publisher._publish_container", side_effect=RuntimeError("timeout")):
    result = publisher.publish("読者に役立つ内容です。", **kwargs)
assert result.success is False
assert result.delivery_state == "CONTAINER_CREATED_PUBLISH_UNVERIFIED"
assert result.container_id == "container-1"

with patch("publishers.threads_publisher._get_credentials", return_value=("token", "user")), patch("publishers.threads_publisher._create_container", side_effect=RuntimeError("bad request")):
    result = publisher.publish("読者に役立つ内容です。", **kwargs)
assert result.delivery_state == "CONTAINER_CREATE_FAILED"
assert result.container_id is None
print("PASS test_threads_publisher_delivery_states.py")
