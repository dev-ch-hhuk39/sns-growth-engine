from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.failures import FailureCategory, classify_failure  # noqa: E402
from acquisition.threads_public import ThreadsPublicHttpAdapter  # noqa: E402


def test_threads_application_404_is_precise_post_discovery_failure():
    adapter = ThreadsPublicHttpAdapter(
        lambda _url: '<html><script>"Barcelona404ErrorRoot"</script></html>'
    )
    result = adapter.discover_profile(
        {
            "source_id": "src_lm_threads",
            "platform": "threads",
            "source_url": "https://www.threads.com/@me01_lsm",
            "target_account_ids": ["liver_manager"],
        },
        limit=5,
    )
    assert result.status == "FAILED"
    assert result.reason == "threads_profile_application_404:me01_lsm"
    assert classify_failure("threads", result.reason) == FailureCategory.POST_DISCOVERY_UNAVAILABLE
