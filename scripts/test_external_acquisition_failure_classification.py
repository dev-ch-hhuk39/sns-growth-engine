#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from acquire_approved_source_posts import classify_external_failure  # noqa: E402

checks = {
    "Threads all fallbacks deferred": classify_external_failure("threads", "all_backends_failed:threads_cli_public:no_public_posts,threads_logged_out_graphql:profile_not_found,threads_public_screen:public_screen_failed") == "DEFERRED",
    "Threads profile links missing": classify_external_failure("threads", "threads_profile_post_links_unavailable") == "POST_DISCOVERY_UNAVAILABLE",
    "Threads detail missing": classify_external_failure("threads", "threads_post_detail_unavailable") == "VIDEO_URL_EXTRACTION_UNAVAILABLE",
    "Threads auth": classify_external_failure("threads", "threads_http_status:403") == "AUTH_REQUIRED",
    "TikTok profile partial failure": classify_external_failure("tiktok", "yt_dlp_discovery_failed:ExtractorError secondary user ID") == "POST_DISCOVERY_UNAVAILABLE",
    "rate limit": classify_external_failure("threads", "http_status:429") == "RATE_LIMITED",
    "timeout unstable": classify_external_failure("tiktok", "TimeoutError") == "BACKEND_UNSTABLE",
}
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
