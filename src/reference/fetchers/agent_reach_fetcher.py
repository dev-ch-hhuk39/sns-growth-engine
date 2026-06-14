"""
agent_reach_fetcher.py - Agent-Reach based Fetcher（Phase 9）

Agent-Reach / browser経由でX/YouTube情報を取得する。
confirm_fetch=True が必要。未インストールなら NOT_INSTALLED。
APIなし方針: X API実呼び出しは禁止。Agent-Reachのlocal browserを経由する。
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import os
from typing import Any

from .base_fetcher import BaseFetcher, FetchResult, RawSourceItem, _now_jst
from .json_import_fetcher import JsonImportFetcher


def _check_agent_reach() -> bool:
    for cmd in [["agent-reach", "--version"], ["npx", "agent-reach", "--version"]]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return True
        except Exception:
            continue
    return False


class AgentReachFetcher(BaseFetcher):
    """Agent-Reach CLI を通じてX/YouTubeの情報を取得する。

    使い方:
      1. Agent-Reach をインストール（npm install -g agent-reach 等）
      2. local browser login / cookie 設定
      3. --fetch --confirm-fetch で実行
    """

    adapter_name = "agent_reach"
    supported_platforms = ["x", "youtube"]

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
                warn="Agent-Reach は local browser login / cookie が必要です。",
            )

        if not confirm_fetch:
            return self._blocked(
                source,
                "--confirm-fetch が指定されていません。実取得をブロックします。",
            )

        if not _check_agent_reach():
            return self._not_installed(
                source,
                "agent-reach (npm install -g agent-reach でインストールしてください)",
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
        cmd = [
            "agent-reach",
            "fetch",
            "--url", url,
            "--platform", platform,
            "--limit", str(max_items),
            "--output", "json",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr[:300] or "Agent-Reach failed")

        try:
            data = json.loads(result.stdout)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("items", data.get("results", [data]))
            return []
        except json.JSONDecodeError:
            raise RuntimeError(f"JSON parse error: {result.stdout[:200]}")
