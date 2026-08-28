#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from gemini_hybrid_client import GeminiHttpError, GeminiHybridClient

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision"],
    "properties": {"decision": {"type": "string", "enum": ["PASS", "REJECT"]}},
}


def main() -> None:
    reservations: list[dict[str, Any]] = []
    bodies: list[dict[str, Any]] = []
    calls = 0

    def reserve(metadata: dict[str, Any]) -> None:
        reservations.append(metadata)

    def transport(_url: str, body: dict[str, Any], _timeout: int) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        bodies.append(body)
        return {
            "candidates": [
                {"content": {"parts": [{"text": json.dumps({"decision": "PASS"})}]}}
            ]
        }

    with tempfile.TemporaryDirectory() as tmp:
        client = GeminiHybridClient(
            api_key="fixture",
            reserve_request=reserve,
            transport=transport,
            cache_dir=Path(tmp),
        )
        first = client.generate_json(
            model="fixture-model",
            prompt="p",
            schema=SCHEMA,
            operation="classify",
            account_id="night_scout",
        )
        second = client.generate_json(
            model="fixture-model",
            prompt="p",
            schema=SCHEMA,
            operation="classify",
            account_id="night_scout",
        )
        assert first["cache_hit"] is False
        assert second["cache_hit"] is True
        assert calls == 1
        assert len(reservations) == 1
        assert client.actual_request_count == 1
        assert "temperature" not in bodies[0]["generationConfig"]

    try:
        GeminiHybridClient(
            api_key="",
            reserve_request=reserve,
            transport=transport,
        ).generate_json(
            model="fixture",
            prompt="p",
            schema=SCHEMA,
            operation="classify",
            account_id="night_scout",
        )
    except RuntimeError as exc:
        assert "missing_GEMINI_API_KEY" in str(exc)
    else:
        raise AssertionError("missing key must fail closed")

    def unavailable(_url: str, _body: dict[str, Any], _timeout: int) -> dict[str, Any]:
        raise GeminiHttpError(503, "fixture unavailable")

    with tempfile.TemporaryDirectory() as tmp:
        try:
            GeminiHybridClient(
                api_key="fixture",
                reserve_request=reserve,
                transport=unavailable,
                cache_dir=Path(tmp),
                max_attempts=1,
            ).generate_json(
                model="fixture-model",
                prompt="p",
                schema=SCHEMA,
                operation="generate",
                account_id="liver_manager",
            )
        except GeminiHttpError as exc:
            assert exc.status_code == 503
            assert exc.operation == "generate"
            assert exc.model == "fixture-model"
            assert exc.retryable is True
        else:
            raise AssertionError("HTTP failure must remain fail closed")
    print("PASS 12 tests")


if __name__ == "__main__":
    main()
