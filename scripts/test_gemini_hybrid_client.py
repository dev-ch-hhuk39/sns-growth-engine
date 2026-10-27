#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import gemini_hybrid_client as gemini  # noqa: E402
from gemini_hybrid_client import GeminiHttpError, GeminiHybridClient  # noqa: E402
from sns_host_ai_budget import HostAIBudgetError  # noqa: E402

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


def _response():
    return {"candidates": [{"content": {"parts": [{"text": '{"decision":"PASS"}'}]}}]}


class HostBudgetTests(unittest.TestCase):
    def setUp(self):
        mode = patch.dict(os.environ, {"SNS_HOST_AI_BUDGET_REQUIRED": "false"})
        mode.start()
        self.addCleanup(mode.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache_dir = Path(self.tmp.name)

    def generate(self, client, **overrides):
        kwargs = dict(model="gemini-fixture", prompt="fixture", schema=SCHEMA,
                      operation="hybrid_review", account_id="night_scout")
        kwargs.update(overrides)
        return client.generate_json(**kwargs)

    def multimodal(self, client, **overrides):
        frame = self.cache_dir / "fixture.jpg"
        frame.write_bytes(b"fixture-image")
        kwargs = dict(model="gemini-fixture", prompt="fixture", schema=SCHEMA,
                      operation="vision_review", account_id="liver_manager", image_paths=[frame])
        kwargs.update(overrides)
        return client.generate_multimodal_json(**kwargs)

    def test_json_retry_counts_each_host_attempt_and_cache_hit_counts_none(self):
        events = []
        responses = iter([GeminiHttpError(503, "fixture"), _response()])

        def transport(_url, body, _timeout):
            events.append("http")
            self.assertNotIn("temperature", body["generationConfig"])
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response

        client = GeminiHybridClient(api_key="fixture", cache_dir=self.cache_dir, transport=transport,
                                    reserve_request=lambda _metadata: events.append("local"))

        def reserve(account, operation):
            self.assertEqual((account, operation), ("night_scout", "hybrid_review"))
            events.append("host")

        with patch.object(gemini, "reserve_host_ai_attempt", side_effect=reserve), patch.object(gemini.time, "sleep"):
            self.assertFalse(self.generate(client)["cache_hit"])
            self.assertTrue(self.generate(client)["cache_hit"])
        self.assertEqual(events, ["local", "host", "http"] * 2)
        self.assertEqual(client.actual_request_count, 2)

    def test_json_host_denial_stops_before_first_or_retried_http(self):
        for deny_at in (1, 2):
            with self.subTest(deny_at=deny_at):
                denial = HostAIBudgetError("execution_limit")
                host = Mock(side_effect=[None] * (deny_at - 1) + [denial])
                transport = Mock(side_effect=GeminiHttpError(503, "fixture"))
                local = Mock()
                client = GeminiHybridClient(api_key="fixture", cache_dir=self.cache_dir,
                                            transport=transport, reserve_request=local)
                with patch.object(gemini, "reserve_host_ai_attempt", host), patch.object(gemini.time, "sleep"):
                    with self.assertRaises(HostAIBudgetError):
                        self.generate(client)
                self.assertEqual((host.call_count, local.call_count), (deny_at, deny_at))
                self.assertEqual(transport.call_count, deny_at - 1)
                self.assertEqual(client.actual_request_count, deny_at - 1)
                self.assertEqual(list(self.cache_dir.glob("*.json")), [])
                self.assertFalse(gemini.retryable_provider_error(denial))

    def test_existing_local_budget_denial_still_prevents_host_and_http(self):
        transport = Mock()
        local = Mock(side_effect=RuntimeError("local_budget_rejected"))
        client = GeminiHybridClient(api_key="fixture", cache_dir=self.cache_dir,
                                    transport=transport, reserve_request=local)
        with patch.object(gemini, "reserve_host_ai_attempt") as host:
            with self.assertRaisesRegex(RuntimeError, "local_budget_rejected"):
                self.generate(client)
        local.assert_called_once()
        host.assert_not_called()
        transport.assert_not_called()

    def test_multimodal_each_retry_reserves_and_preserves_request_settings(self):
        events = []
        responses = iter([GeminiHttpError(503, "fixture"), _response()])

        def transport(_url, body, _timeout):
            events.append("http")
            config = body["generationConfig"]
            self.assertEqual(config["temperature"], 0)
            self.assertEqual(config["maxOutputTokens"], 4096)
            self.assertEqual(config["responseJsonSchema"], SCHEMA)
            self.assertIn("inlineData", body["contents"][0]["parts"][1])
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response

        def reserve(account, operation):
            self.assertEqual((account, operation), ("liver_manager", "vision_review"))
            events.append("host")

        client = GeminiHybridClient(api_key="fixture", transport=transport,
                                    reserve_request=lambda _metadata: events.append("local"))
        with patch.object(gemini, "reserve_host_ai_attempt", side_effect=reserve), patch.object(gemini.time, "sleep"):
            result = self.multimodal(client)
        self.assertEqual(events, ["local", "host", "http"] * 2)
        self.assertEqual(result["actual_requests"], 2)
        self.assertEqual(client.actual_request_count, 2)

    def test_multimodal_host_denial_stops_first_and_retry_attempt(self):
        for deny_at in (1, 2):
            with self.subTest(deny_at=deny_at):
                host = Mock(side_effect=[None] * (deny_at - 1) + [HostAIBudgetError("daily_limit")])
                transport = Mock(side_effect=GeminiHttpError(503, "fixture"))
                local = Mock()
                client = GeminiHybridClient(api_key="fixture", transport=transport, reserve_request=local)
                with patch.object(gemini, "reserve_host_ai_attempt", host), patch.object(gemini.time, "sleep"):
                    with self.assertRaises(HostAIBudgetError):
                        self.multimodal(client)
                self.assertEqual((host.call_count, local.call_count), (deny_at, deny_at))
                self.assertEqual(transport.call_count, deny_at - 1)
                self.assertEqual(client.actual_request_count, deny_at - 1)

    def test_hybrid_explicit_foreign_account_rejected_before_transport(self):
        transport = Mock()
        client = GeminiHybridClient(api_key="fixture", cache_dir=self.cache_dir,
                                    transport=transport, reserve_request=Mock())
        context = {"SNS_HOST_AI_BUDGET_REQUIRED": "true", "SNS_HOST_AI_ACCOUNT_ID": "beauty_account",
                   "SNS_HOST_AI_BUDGET_DIR": "/private/tmp/unused-host-budget-fixture",
                   "SNS_HOST_AI_RUN_ID": "a" * 32, "SNS_HOST_AI_RELEASE": "b" * 40}
        for method in (self.generate, self.multimodal):
            with self.subTest(method=method.__name__), patch.dict(os.environ, context):
                with self.assertRaises(HostAIBudgetError) as caught:
                    method(client)
                self.assertEqual(caught.exception.code, "account_mismatch")
        transport.assert_not_called()


if __name__ == "__main__":
    main()
    unittest.main()
