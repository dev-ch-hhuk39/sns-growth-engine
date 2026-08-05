#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from gemini_hybrid_client import GeminiHybridClient

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision"],
    "properties": {"decision": {"type": "string", "enum": ["PASS", "REJECT"]}},
}


def main() -> None:
    reservations: list[dict[str, Any]] = []
    calls = 0

    def reserve(metadata: dict[str, Any]) -> None:
        reservations.append(metadata)

    def transport(_url: str, _body: dict[str, Any], _timeout: int) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({"decision": "PASS"})}]}}]}

    with tempfile.TemporaryDirectory() as tmp:
        client = GeminiHybridClient(api_key="fixture", reserve_request=reserve, transport=transport, cache_dir=Path(tmp))
        first = client.generate_json(model="fixture-model", prompt="p", schema=SCHEMA, operation="classify", account_id="night_scout")
        second = client.generate_json(model="fixture-model", prompt="p", schema=SCHEMA, operation="classify", account_id="night_scout")
        assert first["cache_hit"] is False
        assert second["cache_hit"] is True
        assert calls == 1
        assert len(reservations) == 1
        assert client.actual_request_count == 1

    try:
        GeminiHybridClient(api_key="", reserve_request=reserve, transport=transport).generate_json(
            model="fixture", prompt="p", schema=SCHEMA, operation="classify", account_id="night_scout"
        )
    except RuntimeError as exc:
        assert "missing_GEMINI_API_KEY" in str(exc)
    else:
        raise AssertionError("missing key must fail closed")
    print("PASS 7 tests")


if __name__ == "__main__":
    main()
