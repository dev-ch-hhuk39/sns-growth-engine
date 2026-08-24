"""Canonical managed-account registry and fail-closed namespace helpers."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = ROOT / "config" / "managed_accounts.json"


def _registry_path() -> Path:
    override = os.environ.get("MANAGED_ACCOUNTS_REGISTRY", "").strip()
    return Path(override) if override else DEFAULT_REGISTRY_PATH


@lru_cache(maxsize=4)
def load_managed_account_registry(path: str = "") -> dict[str, Any]:
    registry_path = Path(path) if path else _registry_path()
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    accounts = data.get("accounts")
    if not isinstance(accounts, dict) or not accounts:
        raise ValueError("managed_account_registry_empty")
    for account_id, record in accounts.items():
        if not account_id or not isinstance(record, dict):
            raise ValueError("managed_account_registry_invalid")
        if not record.get("account_config") or not record.get("credential_prefix"):
            raise ValueError(f"managed_account_registry_incomplete:{account_id}")
        if record.get("x_publish_enabled") is not False:
            raise ValueError(f"managed_account_x_publish_must_be_false:{account_id}")
    return data


def managed_account_ids(*, include_credential_pending: bool = True) -> tuple[str, ...]:
    accounts = load_managed_account_registry()["accounts"]
    return tuple(
        account_id
        for account_id, record in accounts.items()
        if include_credential_pending or str(record.get("status", "")).upper() != "CREDENTIAL_PENDING"
    )


def production_account_ids() -> tuple[str, ...]:
    accounts = load_managed_account_registry()["accounts"]
    return tuple(
        account_id
        for account_id, record in accounts.items()
        if account_production_enabled(account_id)
    )


def account_choices(*, include_all: bool = False, production_only: bool = False) -> tuple[str, ...]:
    values = production_account_ids() if production_only else managed_account_ids()
    return (("all",) + values) if include_all else values


def managed_account(account_id: str) -> dict[str, Any]:
    account = load_managed_account_registry()["accounts"].get(str(account_id or "").strip())
    if not account:
        raise ValueError(f"unmanaged_account:{account_id}")
    return dict(account)


def route_slot_id(account_id: str, route: str) -> str:
    slot_id = str(managed_account(account_id).get("route_slots", {}).get(route, "")).strip()
    if not slot_id:
        raise ValueError(f"managed_account_route_slot_missing:{account_id}:{route}")
    return slot_id


def account_status(account_id: str) -> str:
    record = managed_account(account_id)
    prefix = str(record["credential_prefix"]).upper()
    override = os.environ.get(f"MANAGED_ACCOUNT_STATUS_{prefix}", "").strip().upper()
    return override or str(record.get("status", "")).upper()


def account_production_enabled(account_id: str) -> bool:
    record = managed_account(account_id)
    prefix = str(record["credential_prefix"]).upper()
    override = os.environ.get(f"{prefix}_PRODUCTION_ENABLED", "").strip().lower()
    enabled = (
        override in {"1", "true", "yes", "on"}
        if override
        else bool(record.get("production_enabled"))
    )
    return enabled and account_status(account_id) == "ACTIVE"


def auto_ready_account_ids() -> tuple[str, ...]:
    return tuple(
        account_id
        for account_id in managed_account_ids()
        if str(managed_account(account_id).get("review_policy", "")) == "autonomous_low_risk"
    )


def credential_env_names(account_id: str) -> dict[str, str]:
    prefix = str(managed_account(account_id)["credential_prefix"]).upper()
    return {
        "handle": f"THREADS_HANDLE_{prefix}",
        "user_id": f"THREADS_USER_ID_{prefix}",
        "access_token": f"THREADS_ACCESS_TOKEN_{prefix}",
    }


def require_account_match(expected: str, *records: Mapping[str, Any], allow_global_fact: bool = False) -> None:
    managed_account(expected)
    for record in records:
        scope = str(record.get("scope", "")).strip().lower()
        if allow_global_fact and scope == "global_fact":
            continue
        actual = str(
            record.get("target_account_id")
            or record.get("account_id")
            or record.get("pdca_account_scope")
            or ""
        ).strip()
        if not actual:
            raise ValueError("account_namespace_missing")
        if actual != expected:
            raise ValueError(f"account_namespace_mismatch:{expected}:{actual}")


def filter_account_rows(
    rows: Iterable[Mapping[str, Any]],
    account_id: str,
    *,
    allow_global_fact: bool = False,
) -> list[dict[str, Any]]:
    managed_account(account_id)
    selected: list[dict[str, Any]] = []
    for row in rows:
        scope = str(row.get("scope", "")).strip().lower()
        if allow_global_fact and scope == "global_fact":
            selected.append(dict(row))
            continue
        actual = str(
            row.get("target_account_id")
            or row.get("account_id")
            or row.get("pdca_account_scope")
            or ""
        ).strip()
        if actual == account_id:
            selected.append(dict(row))
    return selected


def invalidate_registry_cache() -> None:
    load_managed_account_registry.cache_clear()
