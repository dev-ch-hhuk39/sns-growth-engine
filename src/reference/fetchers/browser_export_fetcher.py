"""
browser_export_fetcher.py - Browser Export / Manual Fallback Fetcher（Phase 9）

X / Threads / TikTok / YouTube から手動エクスポートしたJSON/CSV/Markdownを取り込む。
Agent-Reach やブラウザ拡張の出力も変換可能。
スクリーンショット・手動コピーは manual_json fallback へ。
"""
from __future__ import annotations

import json
import os
from typing import Any

from .base_fetcher import BaseFetcher, FetchResult, RawSourceItem, _now_jst
from .json_import_fetcher import JsonImportFetcher


class BrowserExportFetcher(BaseFetcher):
    """手動/ブラウザエクスポートデータのインポート。

    対応形式:
      - JSON (list / dict with items key)
      - CSV
      - Markdown (text抽出のみ)
    """

    adapter_name = "browser_export"
    supported_platforms = ["x", "threads", "tiktok", "youtube", "instagram_reels"]

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
        import_path: str = "",
        import_dir: str = "",
    ) -> FetchResult:
        source_id = source.get("source_id", "")

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
                message=f"MOCK: browser_export {len(items)}件のモックデータを返します。",
                mock=True,
                dry_run=dry_run,
                warn="実インポートは --import-path でJSONまたはCSVを指定してください。",
            )

        # import_dirからファイルを探す
        if not import_path and import_dir:
            import_path = self._find_latest_export(import_dir, source.get("source_platform", ""))

        if not import_path:
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="NOT_READY",
                message="import_path が未指定です。--import-path でエクスポートファイルを指定してください。",
                warn="X / Threads / TikTok から手動でエクスポートし、JSONまたはCSVで保存してください。",
            )

        ext = os.path.splitext(import_path)[1].lower()

        if ext == ".md":
            items = self._load_markdown(import_path, source, target_account_id, max_items)
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="OK" if items else "WARN",
                items=items,
                message=f"Markdownから{len(items)}件抽出。",
                warn="Markdownからはtext/titleのみ抽出できます。metricsは空になります。",
                mock=False,
                dry_run=dry_run,
            )

        # JSON / CSV は JsonImportFetcher に委譲
        result = self._json_importer.fetch(
            source,
            target_account_id=target_account_id,
            mock=False,
            dry_run=dry_run,
            confirm_fetch=True,
            max_items=max_items,
            import_path=import_path,
        )

        if result.status == "OK":
            for item in result.items:
                item.fetch_adapter = self.adapter_name
                item.fetch_method = "browser_export"

        return result

    def _find_latest_export(self, directory: str, platform: str) -> str:
        """import_dir から最新のエクスポートファイルを探す。"""
        if not os.path.isdir(directory):
            return ""

        candidates = []
        for fname in os.listdir(directory):
            fpath = os.path.join(directory, fname)
            if not os.path.isfile(fpath):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext not in (".json", ".csv", ".md"):
                continue
            if platform and platform not in fname.lower():
                continue
            candidates.append((os.path.getmtime(fpath), fpath))

        if not candidates:
            return ""

        candidates.sort(reverse=True)
        return candidates[0][1]

    def _load_markdown(
        self,
        path: str,
        source: dict,
        target_account_id: str,
        max_items: int,
    ) -> list[RawSourceItem]:
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return []

        # H2/H3 セクションを投稿として扱う
        import re
        sections = re.split(r"\n#{2,3} ", content)
        items = []
        for i, section in enumerate(sections[:max_items]):
            if not section.strip():
                continue
            lines = section.strip().splitlines()
            title = lines[0].strip().lstrip("#").strip()
            text = "\n".join(lines[1:]).strip() if len(lines) > 1 else title

            item = RawSourceItem(
                source_id=source.get("source_id", ""),
                source_platform=source.get("source_platform", "unknown"),
                source_handle=source.get("source_handle", ""),
                source_url=source.get("source_url", ""),
                target_account_id=target_account_id,
                fetch_adapter=self.adapter_name,
                fetch_method="markdown_import",
                item_type="post",
                post_id=f"md_{i:03d}",
                post_url="",
                text=text[:2000],
                title=title,
                fetched_at=_now_jst(),
                rights_status=source.get("rights_policy", "reference_only"),
                reuse_policy=source.get("reuse_policy", "reference_only"),
                media_policy=source.get("media_policy", "do_not_download"),
            )
            items.append(item)
        return items
