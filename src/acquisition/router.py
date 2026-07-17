"""Backend routing with primary/fallback and a small circuit breaker."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


class BackendFailure(RuntimeError):
    """A recoverable acquisition failure that permits the configured fallback."""


class AcquisitionAdapter(Protocol):
    backend_name: str
    backend_version: str

    def acquire(self, source: dict[str, Any], *, limit: int) -> list[Any]: ...


@dataclass(frozen=True)
class BackendRoute:
    capability: str
    primary: str
    fallbacks: tuple[str, ...] = ()
    cooldown_seconds: int = 900
    shadow: tuple[str, ...] = ()


@dataclass
class BackendState:
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    last_failure_reason: str = ""


@dataclass
class RouteResult:
    backend_name: str
    posts: list[Any]
    attempted_backends: list[str] = field(default_factory=list)
    fallback_used: bool = False
    shadow_results: dict[str, int] = field(default_factory=dict)


class AdapterRouter:
    """Run one PRIMARY adapter and use FALLBACK only after a real failure."""

    def __init__(self, adapters: dict[str, AcquisitionAdapter], routes: dict[str, BackendRoute]):
        self.adapters = adapters
        self.routes = routes
        self.states: dict[str, BackendState] = {name: BackendState() for name in adapters}

    def _available(self, backend_name: str) -> bool:
        return self.states.setdefault(backend_name, BackendState()).cooldown_until <= time.time()

    def _fail(self, backend_name: str, exc: Exception, cooldown_seconds: int) -> None:
        state = self.states.setdefault(backend_name, BackendState())
        state.consecutive_failures += 1
        state.last_failure_reason = f"{type(exc).__name__}:{exc}"[:240]
        state.cooldown_until = time.time() + cooldown_seconds

    def _pass(self, backend_name: str) -> None:
        state = self.states.setdefault(backend_name, BackendState())
        state.consecutive_failures = 0
        state.cooldown_until = 0.0
        state.last_failure_reason = ""

    def route(self, capability: str, source: dict[str, Any], *, limit: int, shadow: bool = False) -> RouteResult:
        route = self.routes[capability]
        choices = (route.primary, *route.fallbacks)
        errors: list[str] = []
        for position, backend_name in enumerate(choices):
            if not self._available(backend_name):
                errors.append(f"{backend_name}:circuit_open")
                continue
            adapter = self.adapters.get(backend_name)
            if not adapter:
                errors.append(f"{backend_name}:not_registered")
                continue
            try:
                posts = adapter.acquire(source, limit=limit)
                self._pass(backend_name)
                result = RouteResult(
                    backend_name=backend_name,
                    posts=posts,
                    attempted_backends=[*errors, backend_name],
                    fallback_used=position > 0,
                )
                if shadow:
                    for shadow_name in route.shadow:
                        shadow_adapter = self.adapters.get(shadow_name)
                        if not shadow_adapter or not self._available(shadow_name):
                            continue
                        try:
                            result.shadow_results[shadow_name] = len(shadow_adapter.acquire(source, limit=limit))
                        except Exception:
                            self._fail(shadow_name, BackendFailure("shadow_failed"), route.cooldown_seconds)
                return result
            except Exception as exc:
                self._fail(backend_name, exc, route.cooldown_seconds)
                errors.append(f"{backend_name}:{type(exc).__name__}")
        raise BackendFailure("all_backends_failed:" + ",".join(errors))

    def health_rows(self) -> list[dict[str, Any]]:
        rows = []
        now = time.time()
        for name, state in sorted(self.states.items()):
            rows.append({
                "backend_name": name,
                "status": "COOLDOWN" if state.cooldown_until > now else "READY",
                "consecutive_failures": state.consecutive_failures,
                "cooldown_until": state.cooldown_until,
                "failure_reason": state.last_failure_reason,
            })
        return rows
