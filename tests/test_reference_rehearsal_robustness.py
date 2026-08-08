from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from src.generation import reference_source_rewriter as rewriter
from src.generation.reference_source_rewriter import ReferenceRewriteError

ROOT = Path(__file__).resolve().parents[1]


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

