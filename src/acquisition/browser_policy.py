"""Keep retained browser adapters outside current owner discovery."""
from __future__ import annotations

from typing import Any

from generation.media_platform_policy import OWNER_REFERENCE_ACCOUNTS

from .router import BackendFailure


def require_legacy_browser_scope(source: dict[str, Any]) -> None:
    """Require explicit non-owner scope before browser or session access.

    Inspect every declared target, including conflicting scalar aliases. An
    omitted or malformed target cannot opt out of the current owner policy.
    This retains legacy parsing without making it an active acquisition route.
    """
    targets = []
    for key in ("account_id", "target_account_id"):
        if source.get(key):
            targets.append(source[key])
    if source.get("target_account_ids") is not None:
        values = source["target_account_ids"]
        if not isinstance(values, (list, tuple)):
            raise BackendFailure("browser_scope_invalid")
        targets.extend(values)
    if not targets or any(not isinstance(value, str) or not value.strip() for value in targets):
        raise BackendFailure("browser_scope_invalid")
    if any(value.strip().lower() in (*OWNER_REFERENCE_ACCOUNTS, "all", "*") for value in targets):
        raise BackendFailure("owner_nonbrowser_discovery_required")
