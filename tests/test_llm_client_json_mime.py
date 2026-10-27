from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import llm_client  # noqa: E402
from sns_host_ai_budget import HostAIBudgetError  # noqa: E402


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "candidates": [{"content": {"parts": [{"text": '{"public_post_text":"ok"}'}]}}]
        }


def test_call_gemini_json_requests_json_mime(monkeypatch) -> None:
    captured = {}

    def post(_url, *, headers, json, timeout, allow_redirects):
        captured["url"] = _url
        captured["headers"] = headers
        captured["allow_redirects"] = allow_redirects
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
    assert "key=" not in captured["url"]
    assert "test-key" not in captured["url"]
    assert captured["headers"] == {"x-goog-api-key": "test-key"}
    assert captured["allow_redirects"] is False


@pytest.fixture
def real_llm_mode(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setattr(llm_client, "_get_api_key", lambda: "fixture")


@pytest.mark.parametrize("explicit_account", [None, "liver_manager", "beauty_account"])
def test_host_reservation_immediately_precedes_generic_http(monkeypatch, real_llm_mode, explicit_account):
    events = []
    monkeypatch.setenv("SNS_HOST_AI_ACCOUNT_ID", "beauty_account")
    monkeypatch.setattr(llm_client, "reserve_host_ai_attempt", lambda account, operation: events.append(("reserve", account, operation)))

    def post(_url, *, headers, json, timeout, allow_redirects):
        events.append(("http",))
        assert json["generationConfig"]["responseMimeType"] == "application/json"
        assert timeout == 90
        assert allow_redirects is False
        return _Response()

    monkeypatch.setattr(llm_client.requests, "post", post)
    kwargs = {} if explicit_account is None else {"account_id": explicit_account}
    assert llm_client.call_gemini_json("return json", **kwargs) == {"public_post_text": "ok"}
    assert events == [
        ("reserve", explicit_account or "beauty_account", "llm_client_generate"), ("http",),
    ]


@pytest.mark.parametrize("call", [llm_client.call_gemini, llm_client.call_gemini_json])
def test_host_denial_propagates_from_generic_wrappers(monkeypatch, real_llm_mode, call):
    reservations = []

    def deny(account, operation):
        reservations.append((account, operation))
        raise HostAIBudgetError("daily_limit")

    monkeypatch.setattr(llm_client, "reserve_host_ai_attempt", deny)
    monkeypatch.setattr(llm_client.requests, "post", lambda *_args, **_kwargs: pytest.fail("HTTP after denied reservation"))
    with pytest.raises(HostAIBudgetError, match="daily_limit"):
        call("fixture", account_id="beauty_account")
    assert reservations == [("beauty_account", "llm_client_generate")]


@pytest.mark.parametrize("account", ["liver_manager", ""])
def test_generic_explicit_mismatch_is_not_replaced_by_pin(monkeypatch, real_llm_mode, account):
    monkeypatch.setenv("SNS_HOST_AI_BUDGET_REQUIRED", "true")
    monkeypatch.setenv("SNS_HOST_AI_BUDGET_DIR", "/private/tmp/unused-host-budget-fixture")
    monkeypatch.setenv("SNS_HOST_AI_RUN_ID", "a" * 32)
    monkeypatch.setenv("SNS_HOST_AI_RELEASE", "b" * 40)
    monkeypatch.setenv("SNS_HOST_AI_ACCOUNT_ID", "beauty_account")
    monkeypatch.setattr(llm_client.requests, "post", lambda *_args, **_kwargs: pytest.fail("HTTP after account mismatch"))
    with pytest.raises(HostAIBudgetError) as caught:
        llm_client.call_gemini_json("fixture", account_id=account)
    assert caught.value.code == "account_mismatch"


@pytest.mark.parametrize("mode", ["DRY_RUN", "MOCK_LLM"])
def test_mock_llm_neither_reads_key_nor_reserves_host(monkeypatch, real_llm_mode, mode):
    monkeypatch.setenv(mode, "true")
    monkeypatch.setattr(llm_client, "_get_api_key", lambda: pytest.fail("mock key lookup"))
    monkeypatch.setattr(llm_client, "reserve_host_ai_attempt", lambda *_args: pytest.fail("mock reservation"))
    monkeypatch.setattr(llm_client.requests, "post", lambda *_args, **_kwargs: pytest.fail("mock HTTP"))
    assert llm_client.call_gemini("fixture")
    assert llm_client.call_gemini_json("fixture", dry_run_mock={"fixture": True}) == {"fixture": True}


def test_generic_legacy_error_still_returns_error_packet(monkeypatch, real_llm_mode):
    monkeypatch.setenv("SNS_HOST_AI_BUDGET_REQUIRED", "false")
    monkeypatch.setattr(llm_client.requests, "post", lambda *_args, **_kwargs: (_ for _ in ()).throw(llm_client.requests.ConnectionError("fixture")))
    assert llm_client.call_gemini_json("fixture") == {"_error": "Gemini API 接続エラー", "_raw": ""}


@pytest.mark.parametrize("status", [403, None])
def test_transport_error_trace_never_includes_private_cause(monkeypatch, real_llm_mode, status):
    import traceback
    from unittest.mock import Mock
    marker="private-transport-fixture-data"
    response=Mock(status_code=status)
    response.raise_for_status.side_effect=llm_client.requests.HTTPError(marker,response=response)
    monkeypatch.setattr(llm_client.requests,'post',lambda *_args,**_kwargs:response)
    with pytest.raises(RuntimeError) as caught:
        llm_client.call_gemini('fixture')
    rendered=''.join(traceback.format_exception(caught.value))
    assert marker not in rendered
    assert caught.value.__suppress_context__


def test_unknown_provider_block_reason_is_not_logged(monkeypatch, real_llm_mode):
    from unittest.mock import Mock
    marker='private-provider-fixture-data'
    response=Mock()
    response.json.return_value={'candidates':[],'promptFeedback':{'blockReason':marker}}
    monkeypatch.setattr(llm_client.requests,'post',lambda *_args,**_kwargs:response)
    result=llm_client.call_gemini_json('fixture')
    assert marker not in str(result)
    assert 'レスポンスが空' in result['_error']
