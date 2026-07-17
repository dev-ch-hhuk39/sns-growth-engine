"""Build the configured production acquisition router."""
from __future__ import annotations

import json
from pathlib import Path

from .router import AdapterRouter, BackendRoute
from .threads_public import ThreadsPublicHttpAdapter, ThreadsPublicProfileAdapter
from .ytdlp import YtDlpProfilePostAdapter

ROOT = Path(__file__).resolve().parents[2]


def load_routing_config() -> dict:
    return json.loads((ROOT / "config" / "source_backend_routing.json").read_text(encoding="utf-8"))


def build_router() -> AdapterRouter:
    config = load_routing_config()
    adapters = {
        "yt_dlp": YtDlpProfilePostAdapter(),
        "threads_public_playwright": ThreadsPublicProfileAdapter(),
        "threads_public_http": ThreadsPublicHttpAdapter(),
    }
    routes = {
        capability: BackendRoute(
            capability=capability,
            primary=str(row["primary"]),
            fallbacks=tuple(row.get("fallbacks", [])),
            shadow=tuple(row.get("shadow", [])),
            cooldown_seconds=int(row.get("cooldown_seconds", 900)),
        )
        for capability, row in config["routes"].items()
        if row["primary"] in adapters
    }
    return AdapterRouter(adapters, routes)
