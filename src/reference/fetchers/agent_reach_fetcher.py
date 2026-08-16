"""Bounded Agent Reach WebChannel integration.

Agent Reach is an installer/doctor/router, not a profile-post scraper.  This
adapter exposes only its generic Jina WebChannel as an optional reference
reader.  It never enables browser sessions, cookies, physical media, or SNS
publishing and it must not be described as native Threads/TikTok support.
"""
from __future__ import annotations

import json
import hashlib
import subprocess
import tempfile
import os
import shutil
from pathlib import Path
from typing import Any

from .base_fetcher import BaseFetcher, FetchResult, RawSourceItem, _now_jst
from .json_import_fetcher import JsonImportFetcher


def _agent_reach_commands() -> list[list[str]]:
    commands: list[list[str]] = []
    executable = shutil.which("agent-reach")
    if executable:
        commands.append([executable, "version"])
    isolated = Path.home() / ".agent-reach-venv" / "bin" / "agent-reach"
    if isolated.is_file():
        commands.append([str(isolated), "version"])
    return commands


def _check_agent_reach() -> bool:
    for cmd in _agent_reach_commands():
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return True
        except Exception:
            continue
    return False


class AgentReachFetcher(BaseFetcher):
    """Use Agent-Reach's real WebChannel as a bounded research fallback.

    Agent-Reach is an installer/doctor, not a profile-post scraper. Production
    profile discovery therefore uses the dedicated acquisition adapters. This
    adapter only invokes the upstream ``WebChannel.read`` API after doctor is
    available; it never invents a nonexistent ``agent-reach fetch`` command.
    """

    adapter_name = "agent_reach"
    supported_platforms = ["web", "youtube", "threads", "tiktok", "x"]

    def __init__(self):
        self._json_importer = JsonImportFetcher()

    def fetch(
        self,
        source: dict[str, Any],
        *,
        target_account_id: str = "",
        mock: bool = True,
        dry_run: bool = True,
        confirm_fetch: bool = False,
        confirm_download: bool = False,
        max_items: int = 10,
        output_path: str = "",
    ) -> FetchResult:
        source_id = source.get("source_id", "")
        platform = source.get("source_platform", "x")

        if mock:
            items = [
                self._make_mock_item(source, target_account_id, i)
                for i in range(min(3, max_items))
            ]
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="OK",
                items=items,
                message=f"MOCK: Agent-Reach {platform} {len(items)}件のモックデータを返します。",
                mock=True,
                dry_run=dry_run,
                warn="Agent Reach mock is reference-only; no browser/cookie/media path is enabled.",
            )

        if not confirm_fetch:
            return self._blocked(
                source,
                "--confirm-fetch が指定されていません。実取得をブロックします。",
            )

        if platform == "x":
            return self._blocked(source, "X network fetch is disabled; Agent-Reach is research-only.")

        if not _check_agent_reach():
            return self._not_installed(
                source,
                "official Agent Reach Python package (isolated venv or requirements-oss.txt)",
            )

        source_url = source.get("source_url", "")
        if not source_url:
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="NOT_READY",
                message="source_url が未設定です。",
            )

        try:
            result_json = self._run_agent_reach(source_url, platform, max_items)
        except Exception as e:
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="ERROR",
                message=f"Agent-Reach 実行エラー: {e}",
            )

        # 出力JSONをjson_import経由で正規化
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(result_json, f, ensure_ascii=False)
            tmp_path = f.name

        try:
            import_result = self._json_importer.fetch(
                source,
                target_account_id=target_account_id,
                mock=False,
                dry_run=dry_run,
                confirm_fetch=True,
                max_items=max_items,
                import_path=tmp_path,
            )
        finally:
            os.unlink(tmp_path)

        return FetchResult(
            adapter=self.adapter_name,
            source_id=source_id,
            status=import_result.status,
            items=import_result.items,
            message=f"Agent-Reach: {import_result.message}",
            mock=False,
            dry_run=dry_run,
        )

    def _run_agent_reach(
        self, url: str, platform: str, max_items: int
    ) -> list[dict]:
        try:
            from agent_reach.channels.web import WebChannel
        except ImportError:
            isolated_python = Path.home() / ".agent-reach-venv" / "bin" / "python"
            if not isolated_python.is_file():
                raise RuntimeError("agent_reach_python_package_unavailable")
            code = (
                "import sys; from agent_reach.channels.web import WebChannel; "
                "sys.stdout.write(WebChannel().read(sys.argv[1]))"
            )
            completed = subprocess.run(
                [str(isolated_python), "-c", code, url],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            if completed.returncode:
                detail = (completed.stderr or "agent_reach_web_channel_failed").strip()
                raise RuntimeError(detail[:400])
            markdown = completed.stdout
        else:
            markdown = WebChannel().read(url)
        text = str(markdown or "").strip()
        if not text:
            raise RuntimeError("agent_reach_web_channel_empty")
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return [{
            "item_type": "web_page_reference",
            "post_id": f"agent_reach_{digest}",
            "post_url": url,
            "title": text.splitlines()[0].lstrip("# ")[:240],
            "text": text[:20000],
            "description": "Bounded Agent-Reach WebChannel research snapshot.",
            "raw_payload_compact": {
                "platform_hint": platform,
                "character_count": len(text),
                "truncated": len(text) > 20000,
            },
        }][:max(1, min(max_items, 1))]
