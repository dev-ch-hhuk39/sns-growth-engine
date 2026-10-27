from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from src.generation import reference_source_rewriter as rewriter
from src.generation.reference_source_rewriter import ReferenceRewriteError

ROOT = Path(__file__).resolve().parents[1]
HostAIBudgetError = rewriter.HostAIBudgetError
_REAL_HOST_RESERVE = rewriter.reserve_host_ai_attempt


def test_threads_login_boilerplate_is_ineligible():
    source = {
        "platform": "threads",
        "original_post_text": "Join Threads to share ideas, ask questions, post random thoughts, find your people and more. Log in with your Instagram.",
    }
    result = rewriter.reference_source_eligibility(source)
    assert result["eligible"] is False
    assert result["reason"] == "threads_login_boilerplate"
    with pytest.raises(ReferenceRewriteError, match="threads_login_boilerplate"):
        rewriter.build_source_material(source)


def test_internal_owned_source_is_ineligible():
    source = {
        "platform": "system_generated_owned",
        "source_account_id": "system_generated",
        "original_post_text": "内部生成済みの投稿本文",
    }
    result = rewriter.reference_source_eligibility(source)
    assert result["eligible"] is False
    assert result["reason"] == "internal_or_self_generated_source"


def test_raw_sheet_original_post_text_is_supported():
    material = rewriter.build_source_material(
        {
            "platform": "threads",
            "source_account_id": "external_creator",
            "original_post_text": "体験入店では客層と黒服の対応を見て、自分に合う店か判断する。",
        }
    )
    assert "体験入店では客層と黒服の対応" in material


def test_semantic_judge_requests_structured_json(monkeypatch):
    captured = {}

    def fake_call(prompt, **kwargs):
        captured.update(kwargs)
        return json.dumps({"pass": True, "reason": "一致"}, ensure_ascii=False)

    monkeypatch.setattr(rewriter, "_call_gemini", fake_call)
    result = rewriter.judge_semantic_fidelity(
        source_material="[post_text_or_caption]\n配信開始時刻を固定する。",
        draft="配信時間を安定させるなら、まず開始時刻を固定してみる。",
    )
    assert result["pass"] is True
    schema = captured["response_schema"]
    assert schema["type"] == "object"
    assert schema["properties"]["pass"]["type"] == "boolean"
    assert set(schema["required"]) == {"pass", "reason"}


def test_gemini_retries_429_without_real_sleep(monkeypatch):
    class FakeResponse:
        def __init__(self, status_code, payload, headers=None):
            self.status_code = status_code
            self._payload = payload
            self.headers = headers or {}

        def json(self):
            return self._payload

    responses = iter(
        [
            FakeResponse(429, {"error": {"details": []}}, {"Retry-After": "1"}),
            FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}),
        ]
    )
    calls = []
    sleeps = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return next(responses)

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("REFERENCE_GEMINI_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("REFERENCE_GEMINI_MAX_ATTEMPTS", "3")
    monkeypatch.setattr(rewriter.requests, "post", fake_post)
    monkeypatch.setattr(rewriter.time, "sleep", lambda seconds: sleeps.append(seconds))
    result = rewriter._call_gemini("test")
    assert result == "ok"
    assert len(calls) == 2
    assert sleeps == [1.0]


def _load_generator_module():
    scripts_dir = str(ROOT / "scripts")
    src_dir = str(ROOT / "src")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    spec = importlib.util.spec_from_file_location(
        "reference_generator_robustness_test",
        ROOT / "scripts/generate_threads_ideas_from_references.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ineligible_high_score_source_does_not_consume_top_n(monkeypatch):
    module = _load_generator_module()
    calls = []

    def fake_rewrite(**kwargs):
        calls.append(kwargs["source"].get("post_id"))
        return {
            "public_post_text": "キャバクラの体験入店では、客層とスタッフ対応を見て自分に合う店か判断したい。\n\n僕なら時給だけで決めず、働きやすさまで確認する。",
            "grounding_summary": {"structure_variant": 1},
            "post_design": {},
            "generation_policy": {},
        }

    validation = {
        "status": "PASS",
        "blocked_reasons": [],
        "internal_leak_check": {"status": "PASS"},
        "account_fit_check": {"status": "PASS"},
        "public_post_quality_score": 90,
        "reader_value_score": 90,
        "naturalness_score": 90,
        "cta_pressure_score": 0,
    }
    monkeypatch.setattr(module, "rewrite_reference_post", fake_rewrite)
    monkeypatch.setattr(module, "final_public_post_validator", lambda *args, **kwargs: validation)
    monkeypatch.setattr(
        module,
        "_reference_quality",
        lambda *args, **kwargs: {"status": "PASS", "batch_diversity_status": "PASS", "primary_topic": "source_grounded"},
    )
    monkeypatch.setattr(module, "_feature_fields", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        module,
        "build_rewritten_post_candidate",
        lambda **kwargs: {"status": "WAITING_REVIEW", "similarity_guard": {"similarity": 0.1, "status": "PASS"}},
    )

    posts = [
        {
            "post_id": "bad",
            "account_id": "night_scout",
            "platform": "system_generated_owned",
            "source_account_id": "system_generated",
            "post_text": "内部生成済み投稿",
        },
        {
            "post_id": "good",
            "account_id": "night_scout",
            "platform": "threads",
            "source_account_id": "external_creator",
            "post_text": "体験入店では客層とスタッフ対応を見る。",
        },
    ]
    scores = [
        {"reference_post_id": "bad", "account_id": "night_scout", "total_score": "100", "cta_score": "90"},
        {"reference_post_id": "good", "account_id": "night_scout", "total_score": "90", "cta_score": "80"},
    ]
    rows = module.build_generation_rows(account_id="night_scout", posts=posts, scores=scores, top_n=1)
    assert len(rows["queue"]) == 1
    assert calls == ["good"]
    assert rows["drafts"][0]["source_refs"] == "good"


def test_structured_request_uses_generate_content_compatible_fields(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {}

        def json(self):
            return {
                "candidates": [
                    {"content": {"parts": [{"text": '{"pass":true,"reason":"ok"}'}]}}
                ]
            }

    def fake_post(*args, **kwargs):
        captured.update(kwargs)
        return FakeResponse()

    schema = {
        "type": "object",
        "properties": {
            "pass": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["pass", "reason"],
    }
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("REFERENCE_GEMINI_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setattr(rewriter.requests, "post", fake_post)
    result = rewriter._call_gemini("judge", response_schema=schema)
    assert json.loads(result)["pass"] is True
    generation_config = captured["json"]["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["responseSchema"] == schema
    assert "responseFormat" not in generation_config


def test_http_400_reports_safe_google_status_without_request_headers(monkeypatch):
    class FakeResponse:
        status_code = 400
        headers = {}

        def json(self):
            return {
                "error": {
                    "status": "INVALID_ARGUMENT",
                    "message": 'Unknown field. api_key=super-secret-value',
                }
            }

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("REFERENCE_GEMINI_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setattr(rewriter.requests, "post", lambda *args, **kwargs: FakeResponse())
    with pytest.raises(ReferenceRewriteError) as caught:
        rewriter._call_gemini("test")
    message = str(caught.value)
    assert "HTTP 400" in message
    assert "INVALID_ARGUMENT" in message
    assert "super-secret-value" not in message


def test_gemini3_uses_low_thinking_by_default(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {}

        def json(self):
            return {
                "candidates": [
                    {"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}
                ]
            }

    def fake_post(*args, **kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("REFERENCE_GEMINI_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.delenv("REFERENCE_GEMINI_THINKING_LEVEL", raising=False)
    monkeypatch.setattr(rewriter.requests, "post", fake_post)
    assert rewriter._call_gemini("test", model="gemini-3.6-flash") == "ok"
    config = captured["json"]["generationConfig"]
    assert config["thinkingConfig"] == {"thinkingLevel": "low"}


def test_empty_parts_reports_finish_reason_and_usage(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {}

        def json(self):
            return {
                "candidates": [
                    {"content": {"role": "model"}, "finishReason": "MAX_TOKENS"}
                ],
                "usageMetadata": {
                    "thoughtsTokenCount": 80,
                    "candidatesTokenCount": 0,
                },
            }

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("REFERENCE_GEMINI_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setattr(rewriter.requests, "post", lambda *args, **kwargs: FakeResponse())
    with pytest.raises(ReferenceRewriteError) as caught:
        rewriter._call_gemini("test", model="gemini-3.6-flash", max_output_tokens=80)
    message = str(caught.value)
    assert "MAX_TOKENS" in message
    assert "thoughtsTokenCount=80" in message
    assert "candidatesTokenCount=0" in message


def test_thought_parts_are_not_returned_as_public_text(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {}

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"thought": True, "text": "internal reasoning"},
                                {"text": '{"pass":true,"reason":"ok"}'},
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ]
            }

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("REFERENCE_GEMINI_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setattr(rewriter.requests, "post", lambda *args, **kwargs: FakeResponse())
    result = rewriter._call_gemini("test", model="gemini-3.6-flash")
    assert "internal reasoning" not in result
    assert json.loads(result)["pass"] is True


class _BudgetResponse:
    headers = {}

    def __init__(self, text="ok", status_code=200):
        self.status_code = status_code
        self.text = text

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": self.text}]}}]}


@pytest.fixture
def host_reference_transport(monkeypatch):
    events = []
    monkeypatch.setenv("REFERENCE_GEMINI_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("REFERENCE_GEMINI_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("REFERENCE_GEMINI_FALLBACK_MODEL", "secondary")
    monkeypatch.setattr(rewriter, "_api_key", lambda: "fixture")
    monkeypatch.setattr(rewriter.time, "sleep", lambda _seconds: None)

    def reserve(account_id, operation):
        events.append(("reserve", account_id, operation))

    monkeypatch.setattr(rewriter, "reserve_host_ai_attempt", reserve)
    return events


def _budget_rewrite():
    return rewriter.rewrite_reference_post(
        account_id="liver_manager",
        source={"platform": "threads", "text": "配信を始める時刻を固定すると、視聴者が予定を立てやすい。"},
        model="primary",
    )


_BUDGET_DRAFT = "配信時間が毎日ずれるなら、まず開始時刻を固定してみて。視聴者が予定を立てやすくなり、次の配信にも来てもらいやすくなる。"


def test_host_reserves_draft_and_judge_separately(monkeypatch, host_reference_transport):
    events = host_reference_transport
    # An available explicit caller account must survive even a foreign pin.
    monkeypatch.setenv("SNS_HOST_AI_ACCOUNT_ID", "night_scout")
    responses = iter([_BudgetResponse(_BUDGET_DRAFT), _BudgetResponse('{"pass":true,"reason":"ok"}')])

    def post(*_args, **_kwargs):
        events.append(("http",))
        return next(responses)

    monkeypatch.setattr(rewriter.requests, "post", post)
    assert _budget_rewrite()["semantic_fidelity"]["pass"] is True
    assert events == [
        ("reserve", "liver_manager", "reference_rewrite"), ("http",),
        ("reserve", "liver_manager", "reference_semantic_judge"), ("http",),
    ]


def test_host_reserves_every_retry_and_model_fallback(monkeypatch, host_reference_transport):
    events = host_reference_transport
    responses = iter([
        rewriter.requests.ConnectionError("fixture"), _BudgetResponse(status_code=503),
        _BudgetResponse(_BUDGET_DRAFT), _BudgetResponse('{"pass":true,"reason":"ok"}'),
    ])

    def post(url, **_kwargs):
        events.append(("http", "secondary" if "/secondary:" in url else "primary"))
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(rewriter.requests, "post", post)
    assert _budget_rewrite()["generation_failover_reason"] == "PRIMARY_PROVIDER_UNAVAILABLE"
    assert events == [
        ("reserve", "liver_manager", "reference_rewrite"), ("http", "primary"),
        ("reserve", "liver_manager", "reference_rewrite"), ("http", "primary"),
        ("reserve", "liver_manager", "reference_rewrite"), ("http", "secondary"),
        ("reserve", "liver_manager", "reference_semantic_judge"), ("http", "secondary"),
    ]


@pytest.mark.parametrize("deny_at", [1, 2])
def test_host_denial_never_retries_or_accepts_unjudged_draft(
    monkeypatch, host_reference_transport, deny_at,
):
    events = host_reference_transport
    reservations = 0

    def reserve(account_id, operation):
        nonlocal reservations
        reservations += 1
        events.append(("reserve", account_id, operation))
        if reservations == deny_at:
            raise HostAIBudgetError("execution_limit")

    def post(*_args, **_kwargs):
        events.append(("http",))
        return _BudgetResponse(_BUDGET_DRAFT)

    monkeypatch.setattr(rewriter, "reserve_host_ai_attempt", reserve)
    monkeypatch.setattr(rewriter.requests, "post", post)
    with pytest.raises(HostAIBudgetError, match="execution_limit"):
        _budget_rewrite()
    assert reservations == deny_at
    assert events.count(("http",)) == deny_at - 1


def test_host_explicit_foreign_account_is_rejected_before_http(monkeypatch, host_reference_transport):
    monkeypatch.setenv("SNS_HOST_AI_BUDGET_REQUIRED", "true")
    monkeypatch.setenv("SNS_HOST_AI_BUDGET_DIR", "/private/tmp/unused-host-budget-fixture")
    monkeypatch.setenv("SNS_HOST_AI_RUN_ID", "a" * 32)
    monkeypatch.setenv("SNS_HOST_AI_RELEASE", "b" * 40)
    monkeypatch.setenv("SNS_HOST_AI_ACCOUNT_ID", "night_scout")
    monkeypatch.setattr(rewriter, "reserve_host_ai_attempt", _REAL_HOST_RESERVE)
    monkeypatch.setattr(rewriter.requests, "post", lambda *_args, **_kwargs: pytest.fail("HTTP after account mismatch"))
    with pytest.raises(HostAIBudgetError) as caught:
        _budget_rewrite()
    assert caught.value.code == "account_mismatch"


def test_host_legacy_request_needs_no_protected_context(monkeypatch, host_reference_transport):
    monkeypatch.setenv("SNS_HOST_AI_BUDGET_REQUIRED", "false")
    for name in ("SNS_HOST_AI_BUDGET_DIR", "SNS_HOST_AI_RUN_ID", "SNS_HOST_AI_RELEASE", "SNS_HOST_AI_ACCOUNT_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(rewriter, "reserve_host_ai_attempt", _REAL_HOST_RESERVE)
    monkeypatch.setattr(rewriter.requests, "post", lambda *_args, **_kwargs: _BudgetResponse())
    assert rewriter._call_gemini("legacy") == "ok"

