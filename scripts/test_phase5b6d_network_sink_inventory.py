#!/usr/bin/env python3
"""5B-6D static network sink inventory + live helper fail-closed regression.

This inventory catches accidental new HTTP POST sinks in repo Python code.
It is a conservative source check, not a substitute for runtime egress ACL,
code review, dependency audits or the common VPS deployment boundary.
"""
from __future__ import annotations

import ast
import collections
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from publishers.threads_publisher import (  # noqa: E402
    _create_carousel_container, _create_container,
)

# Review/approve exact sink counts if a legitimate provider or transport
# changes. New code silently adding a POST route must not pass PR CI.
EXPECTED = {
    "scripts/gemini_hybrid_client.py": {"urllib.Request:POST": 1},
    # The only new transport is a fixed localhost Ollama inference endpoint,
    # not a Meta/Cloudinary/Google external publisher or a paid API.
    "scripts/sns_local_ollama_draft_bank.py": {"urllib.Request:POST": 1},
    "src/transcription/cloudflare_whisper_client.py": {
        "urllib.Request:POST": 1,
    },
    "src/generation/reference_source_rewriter.py": {"requests.post": 1},
    "src/generation/source_grounded_caption.py": {"requests.post": 1},
    "src/llm_client.py": {"requests.post": 1},
    "src/media/cloudinary_client.py": {"requests.post": 1},
    "src/publishers/threads_publisher.py": {"requests.post": 4},
    "src/publishers/x_publisher.py": {"requests.post": 1},
}
THREADS_WRITER = "src/publishers/threads_publisher.py"
LOW_LEVEL_HELPERS = frozenset({
    "_create_container", "_create_carousel_container", "_publish_container",
})


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _name(node.value) + "." + node.attr
    return ""


def _verb(call: ast.Call) -> bool:
    if call.args and isinstance(call.args[0], ast.Constant):
        return str(call.args[0].value).upper() in {"POST", "PUT", "PATCH", "DELETE"}
    return any(
        field.arg == "method"
        and isinstance(field.value, ast.Constant)
        and str(field.value.value).upper() in {"POST", "PUT", "PATCH", "DELETE"}
        for field in call.keywords
    )


def _urllib_post(call: ast.Call) -> bool:
    if _name(call.func) != "urllib.request.Request":
        return False
    if _verb(call):
        return True
    return any(
        kw.arg == "data" and not (
            isinstance(kw.value, ast.Constant) and kw.value.value is None
        )
        for kw in call.keywords
    )


def _sinks(code: str) -> collections.Counter[str]:
    tree = ast.parse(code)
    found: collections.Counter[str] = collections.Counter()
    for item in ast.walk(tree):
        if not isinstance(item, ast.Call):
            continue
        target = _name(item.func)
        if target in {"requests.post", "httpx.post"}:
            found[target] += 1
        elif target in {"requests.request", "httpx.request"} and _verb(item):
            found[target + ":write"] += 1
        elif target.endswith(".post") and target.split(".")[0] in {
            "session", "http", "client", "api", "sender",
        }:
            found["generic_session.post"] += 1
        elif _urllib_post(item):
            found["urllib.Request:POST"] += 1
    return found


def _all_sinks() -> dict[str, dict[str, int]]:
    seen = {}
    for folder in ("src", "scripts"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            if path.name.startswith("test_"):
                continue
            relative = path.relative_to(ROOT).as_posix()
            found = _sinks(path.read_text(encoding="utf-8"))
            if found:
                seen[relative] = dict(found)
    return seen


def _forbidden_helper_imports() -> list[str]:
    problems = []
    for folder in ("src", "scripts"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            if path.name.startswith("test_"):
                continue
            relative = path.relative_to(ROOT).as_posix()
            if relative == THREADS_WRITER:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for item in ast.walk(tree):
                if isinstance(item, ast.ImportFrom) and item.module and (
                    item.module.endswith("threads_publisher")
                ) and LOW_LEVEL_HELPERS.intersection(
                    imp.name for imp in item.names
                ):
                    problems.append(relative + ":private_threads_import")
                if isinstance(item, ast.Call) and (
                    _name(item.func) in LOW_LEVEL_HELPERS
                    or (_name(item.func).startswith("threads_publisher.")
                        and _name(item.func).rsplit(".", 1)[-1] in LOW_LEVEL_HELPERS)
                ):
                    problems.append(relative + ":private_threads_call")
    return problems


class NetworkSinkInventoryTests(unittest.TestCase):
    def test_exact_network_post_inventory(self):
        self.assertEqual(_all_sinks(), EXPECTED)

    def test_ollama_sink_is_fixed_localhost_and_no_redirect(self):
        script = ROOT / "scripts" / "sns_local_ollama_draft_bank.py"
        source = script.read_text(encoding="utf-8")
        self.assertIn('URL = "http://127.0.0.1:11434/api/generate"', source)
        self.assertIn("class NoRedirect(urllib.request.HTTPRedirectHandler)", source)
        self.assertIn("urllib.request.build_opener(NoRedirect())", source)
        self.assertNotIn("urllib.request.urlopen(request", source)
        self.assertNotIn("https://graph.threads.net", source)
        self.assertNotIn("https://api.openai.com", source)

    def test_private_threads_post_helpers_have_no_new_callers(self):
        self.assertEqual(_forbidden_helper_imports(), [])

    def test_checker_catches_extra_sns_post_and_urllib_writes(self):
        code = (
            'import requests\n'
            'requests.post("https://graph.threads.net/v1.0/id/threads_publish")\n'
            'import urllib.request\n'
            'urllib.request.Request("https://graph.threads.net", data=b"x")\n'
        )
        self.assertEqual(
            _sinks(code),
            {"requests.post": 1, "urllib.Request:POST": 1},
        )

    def test_direct_threads_media_container_is_denied_before_network(self):
        all_flags = {
            "PUBLISH_ENABLED": "true", "ALLOW_REAL_THREADS_POST": "true",
            "ALLOW_MEDIA_POSTS": "true", "ALLOW_REAL_THREADS_VIDEO_POST": "true",
            "ALLOW_THREADS_CAROUSEL": "true", "ALLOW_THREADS_MIXED_CAROUSEL": "true",
        }
        with patch.dict(os.environ, all_flags), patch(
            "requests.post",
            side_effect=AssertionError("unexpected SNS network call"),
        ):
            for media_type, url in (
                ("IMAGE", "https://cdn.example/asset.png"),
                ("VIDEO", "https://cdn.example/asset.mp4"),
                ("CAROUSEL", "https://cdn.example/asset.png"),
                ("TEXT", "https://cdn.example/unexpected-asset.png"),
                ("IMAGE", None),
            ):
                with self.subTest(media_type=media_type, media_url=url):
                    with self.assertRaisesRegex(
                        PermissionError, "MEDIA_AUTHORITY_NOT_CONNECTED",
                    ):
                        _create_container(
                            "user_id", "placeholder_token", "text",
                            media_type=media_type, media_url=url,
                        )

    def test_direct_carousel_helper_is_denied_before_network(self):
        with patch("requests.post", side_effect=AssertionError("unexpected SNS call")):
            with self.assertRaisesRegex(
                PermissionError, "MEDIA_AUTHORITY_NOT_CONNECTED",
            ):
                _create_carousel_container(
                    "user_id", "placeholder_token", "text",
                    ["https://cdn.example/1.jpg"], ["IMAGE"],
                )

    def test_dispatch_guard_module_has_no_external_http_sender(self):
        file = (ROOT / "scripts" / "media_dispatch_guard.py").read_text()
        for call in ("requests.post(", "urllib.request.Request(",
                     "get_publisher(", "_create_container(",
                     "update_queue_item(", "publish_authorized=True"):
            self.assertNotIn(call, file)


if __name__ == "__main__":
    unittest.main()
