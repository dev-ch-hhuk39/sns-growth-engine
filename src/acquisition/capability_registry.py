"""Machine-readable acquisition capabilities and production route policy."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = ROOT / "config" / "acquisition_backend_capabilities.json"

PRODUCTION_ROLES = {"PRIMARY", "FALLBACK", "SHADOW"}
FALLBACK_ROLES = PRODUCTION_ROLES | {"OPTIONAL_AUTH"}
VALID_ROLES = FALLBACK_ROLES | {
    "ANALYSIS_ONLY",
    "BENCHMARK_ONLY",
    "NOT_USED_BY_OWNER_POLICY",
    "REJECTED",
}


@dataclass(frozen=True)
class BackendCapability:
    backend_id: str
    platforms: tuple[str, ...]
    route_capabilities: tuple[str, ...]
    capabilities: tuple[str, ...]
    role: str
    requires_auth: bool
    requires_browser: bool
    requires_external_service: bool
    read_only: bool
    physical_media: bool
    pin: str
    revision: str
    license: str
    health: str
    bounded_limit: int
    raw: dict[str, Any]

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "BackendCapability":
        role = str(row.get("role", "REJECTED"))
        if role not in VALID_ROLES:
            raise ValueError(f"unsupported_backend_role:{role}")
        return cls(
            backend_id=str(row["backend_id"]),
            platforms=tuple(str(value) for value in row.get("platforms", [])),
            route_capabilities=tuple(str(value) for value in row.get("route_capabilities", [])),
            capabilities=tuple(str(value) for value in row.get("capabilities", [])),
            role=role,
            requires_auth=row.get("requires_auth") is True,
            requires_browser=row.get("requires_browser") is True,
            requires_external_service=row.get("requires_external_service") is True,
            read_only=row.get("read_only") is True,
            physical_media=row.get("physical_media") is True,
            pin=str(row.get("pin", "")),
            revision=str(row.get("revision", "")),
            license=str(row.get("license", "NOASSERTION")),
            health=str(row.get("health", "UNKNOWN")),
            bounded_limit=int(row.get("bounded_limit", 0)),
            raw=dict(row),
        )

    @property
    def production_selectable(self) -> bool:
        return (
            self.role in PRODUCTION_ROLES
            and not self.requires_auth
            and not self.requires_browser
            and not self.requires_external_service
            and self.read_only
            and self.bounded_limit > 0
        )


class CapabilityRegistry:
    def __init__(
        self,
        rows: list[dict[str, Any]],
        policy: dict[str, Any] | None = None,
        future_platforms: list[dict[str, Any]] | None = None,
    ):
        parsed = [BackendCapability.from_mapping(row) for row in rows]
        self.backends = {row.backend_id: row for row in parsed}
        if len(self.backends) != len(parsed):
            raise ValueError("duplicate_backend_id")
        self.policy = dict(policy or {})
        self.future_platforms = [dict(row) for row in (future_platforms or [])]

    @classmethod
    def load(cls, path: Path = DEFAULT_REGISTRY_PATH) -> "CapabilityRegistry":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            payload.get("backends", []),
            payload.get("policy", {}),
            payload.get("future_platforms", []),
        )

    def get(self, backend_id: str) -> BackendCapability:
        try:
            return self.backends[backend_id]
        except KeyError as exc:
            raise ValueError(f"backend_not_in_capability_registry:{backend_id}") from exc

    def supports_route(self, backend_id: str, route_capability: str) -> bool:
        return route_capability in self.get(backend_id).route_capabilities

    def require_production_route(self, backend_id: str, route_capability: str) -> None:
        backend = self.get(backend_id)
        if not self.supports_route(backend_id, route_capability):
            raise ValueError(f"backend_capability_mismatch:{backend_id}:{route_capability}")
        if not backend.production_selectable:
            raise ValueError(f"backend_not_production_selectable:{backend_id}")

    def require_fallback_route(self, backend_id: str, route_capability: str) -> None:
        backend = self.get(backend_id)
        if not self.supports_route(backend_id, route_capability):
            raise ValueError(f"backend_capability_mismatch:{backend_id}:{route_capability}")
        if (
            backend.role not in FALLBACK_ROLES
            or backend.requires_browser
            or backend.requires_external_service
            or not backend.read_only
            or backend.bounded_limit <= 0
        ):
            raise ValueError(f"backend_not_fallback_selectable:{backend_id}")

    def validate_routes(self, routes: dict[str, Any], *, registered: set[str]) -> list[str]:
        errors: list[str] = []
        for capability, route in routes.items():
            for position, backend_id in enumerate((route.primary, *route.fallbacks)):
                if backend_id not in registered:
                    errors.append(f"backend_not_registered:{capability}:{backend_id}")
                    continue
                try:
                    if position == 0:
                        self.require_production_route(backend_id, capability)
                    else:
                        self.require_fallback_route(backend_id, capability)
                except ValueError as exc:
                    errors.append(str(exc))
        return errors

    def matrix(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key in sorted(self.backends):
            backend = self.backends[key]
            row = dict(backend.raw)
            row.setdefault("install_runtime_requirement", row.get("supported_runtime", ""))
            row.setdefault("auth_requirement", "REQUIRED" if backend.requires_auth else "NONE")
            row.setdefault("browser_requirement", "REQUIRED" if backend.requires_browser else "NONE")
            row.setdefault("live_evidence_status", backend.health)
            row.setdefault("last_verified_at", "2026-08-11")
            row.setdefault("failure_mode", backend.health if "PASS" not in backend.health and "READY" not in backend.health else "")
            row.setdefault(
                "security_privacy_notes",
                "Read-only; credentials are runtime-only and never included in reports."
                if backend.requires_auth
                else "Read-only bounded acquisition; no browser credential extraction.",
            )
            rows.append(row)
        return rows

    def future_platform_matrix(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.future_platforms]
