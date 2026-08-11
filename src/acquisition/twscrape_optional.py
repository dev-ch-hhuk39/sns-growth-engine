"""Disabled-by-default twscrape capability detector.

The active X physical route remains yt-dlp. This adapter deliberately does not
collect credentials or browser cookies; it only exposes the exact requirement
for a future owner-approved structured timeline route.
"""
from __future__ import annotations

import importlib.util
import os
from typing import Any

from .contracts import ProviderResult


class TwscrapeOptionalAdapter:
    backend_name = "twscrape"
    backend_version = "9745b021d8a7405bed8bc56a725813367b3f07dd"

    @staticmethod
    def capability_status() -> ProviderResult[dict[str, Any]]:
        installed = importlib.util.find_spec("twscrape") is not None
        auth_present = bool(os.environ.get("TWSCRAPE_AUTH_TOKEN")) and bool(
            os.environ.get("TWSCRAPE_CT0")
        )
        if not installed:
            return ProviderResult(
                "twscrape",
                TwscrapeOptionalAdapter.backend_version,
                "UNAVAILABLE",
                reason="TOOL_NOT_INSTALLED",
                data={"installed": False, "auth_present": auth_present, "active": False},
            )
        if not auth_present:
            return ProviderResult(
                "twscrape",
                TwscrapeOptionalAdapter.backend_version,
                "BLOCKED",
                reason="AUTH_REQUIRED:auth_token_and_ct0",
                data={"installed": True, "auth_present": False, "active": False},
            )
        return ProviderResult(
            "twscrape",
            TwscrapeOptionalAdapter.backend_version,
            "BLOCKED",
            reason="OPTIONAL_AUTH_BACKEND_DISABLED_BY_DEFAULT",
            data={"installed": True, "auth_present": True, "active": False},
        )

    def discover_profile(self, source: dict[str, Any], *, limit: int) -> ProviderResult[list[Any]]:
        del source, limit
        status = self.capability_status()
        return ProviderResult(
            self.backend_name,
            self.backend_version,
            status.status,
            data=[],
            reason=status.reason,
            retryable=False,
            metadata=status.data or {},
        )
