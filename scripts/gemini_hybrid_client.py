#!/usr/bin/env python3
"""Gemini JSON client with cache-before-budget and fail-closed validation."""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from hybrid_ai_budget import reserve as local_reserve

CACHE_DIR = Path(os.environ.get("GEMINI_CACHE_DIR", ".runtime/gemini_cache"))
DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("GEMINI_TIMEOUT_SECONDS", "60"))
DEFAULT_MAX_ATTEMPTS = int(os.environ.get("GEMINI_MAX_ATTEMPTS", "2"))


class GeminiHttpError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(f"gemini_http_error:{status_code}:{detail[:400]}")
        self.status_code = status_code
        self.operation = ""
        self.model = ""
        self.retryable = status_code in {429, 500, 502, 503, 504}


def _schema_hash(schema: Mapping[str, Any]) -> str:
    raw = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_key(model: str, prompt: str, schema: Mapping[str, Any], operation: str) -> str:
    raw = "\n".join([model, operation, _schema_hash(schema), prompt])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_schema(value: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            raise RuntimeError(f"gemini_schema_invalid:{path}:expected_object")
        for key in schema.get("required", []):
            if key not in value:
                raise RuntimeError(f"gemini_schema_invalid:{path}.{key}:missing")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise RuntimeError(f"gemini_schema_invalid:{path}:extra_keys:{extra}")
        for key, child in properties.items():
            if key in value:
                _validate_schema(value[key], child, f"{path}.{key}")
    elif expected == "array":
        if not isinstance(value, list):
            raise RuntimeError(f"gemini_schema_invalid:{path}:expected_array")
        item_schema = schema.get("items", {})
        for index, item in enumerate(value):
            _validate_schema(item, item_schema, f"{path}[{index}]")
    elif expected == "string":
        if not isinstance(value, str):
            raise RuntimeError(f"gemini_schema_invalid:{path}:expected_string")
        if "enum" in schema and value not in schema["enum"]:
            raise RuntimeError(f"gemini_schema_invalid:{path}:enum:{value}")
        if int(schema.get("minLength", 0)) > len(value):
            raise RuntimeError(f"gemini_schema_invalid:{path}:too_short")
    elif expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        raise RuntimeError(f"gemini_schema_invalid:{path}:expected_integer")
    elif expected == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
        raise RuntimeError(f"gemini_schema_invalid:{path}:expected_number")
    elif expected == "boolean" and not isinstance(value, bool):
        raise RuntimeError(f"gemini_schema_invalid:{path}:expected_boolean")


def _default_transport(url: str, body: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GeminiHttpError(exc.code, detail) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"gemini_network_error:{exc.reason}") from exc


def _extract_json(response: Mapping[str, Any]) -> dict[str, Any]:
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("gemini_response_missing_candidates")
    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    texts = [str(part.get("text", "")) for part in parts if str(part.get("text", "")).strip()]
    if not texts:
        raise RuntimeError("gemini_response_missing_text")
    raw = "\n".join(texts).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].lstrip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gemini_response_invalid_json:{exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("gemini_response_not_object")
    return value


class GeminiHybridClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        reserve_request: Callable[[dict[str, Any]], Any] | None = None,
        transport: Callable[[str, dict[str, Any], int], dict[str, Any]] | None = None,
        cache_dir: Path | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")).strip()
        self.reserve_request = reserve_request or (lambda metadata: local_reserve(1, metadata))
        self.transport = transport or _default_transport
        self.cache_dir = cache_dir or CACHE_DIR
        self.timeout_seconds = max(1, timeout_seconds)
        self.max_attempts = max(1, min(max_attempts, 2))
        self.actual_request_count = 0

    def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        schema: Mapping[str, Any],
        operation: str,
        account_id: str,
        cache_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("missing_GEMINI_API_KEY")
        key_prompt = prompt + "\nCACHE_CONTEXT=" + json.dumps(cache_context or {}, ensure_ascii=False, sort_keys=True)
        cache_key = _cache_key(model, key_prompt, schema, operation)
        cache_path = self.cache_dir / f"{cache_key}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            _validate_schema(cached["data"], schema)
            return {**cached, "cache_hit": True, "actual_requests": 0}

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": dict(schema),
            },
        }
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            request_id = f"hybrid_ai_{uuid.uuid4().hex}"
            metadata = {
                "request_id": request_id,
                "operation": operation,
                "account_id": account_id,
                "model": model,
                "attempt": attempt,
                "cache_key": cache_key,
            }
            self.reserve_request(metadata)
            self.actual_request_count += 1
            try:
                response = self.transport(url, body, self.timeout_seconds)
                data = _extract_json(response)
                _validate_schema(data, schema)
                result = {
                    "data": data,
                    "model": model,
                    "operation": operation,
                    "request_id": request_id,
                    "cache_key": cache_key,
                    "cache_hit": False,
                    "actual_requests": 1,
                }
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                temp = cache_path.with_suffix(".tmp")
                temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                os.replace(temp, cache_path)
                return result
            except GeminiHttpError as exc:
                exc.operation = operation
                exc.model = model
                last_error = exc
                if not exc.retryable or attempt >= self.max_attempts:
                    raise
            except RuntimeError as exc:
                last_error = exc
                if attempt >= self.max_attempts:
                    raise
            time.sleep(2)
        raise RuntimeError(f"gemini_request_failed:{last_error}")
