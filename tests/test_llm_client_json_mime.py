from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import llm_client  # noqa: E402


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "candidates": [{"content": {"parts": [{"text": '{"public_post_text":"ok"}'}]}}]
        }


def test_call_gemini_json_requests_json_mime(monkeypatch) -> None:
    captured = {}

    def post(_url, *, json, timeout):
        captured["payload"] = json
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setattr(llm_client.requests, "post", post)

    result = llm_client.call_gemini_json("return json")
    assert result == {"public_post_text": "ok"}
    assert captured["payload"]["generationConfig"]["responseMimeType"] == "application/json"
