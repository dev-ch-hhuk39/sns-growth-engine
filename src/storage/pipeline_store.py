#!/usr/bin/env python3
"""pipeline_store.py - パイプライン出力の JSON 保存"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


_DEFAULT_OUTPUT_DIR = "output/pipeline_runs"


class PipelineStore:
    """run_id ごとにパイプライン出力を JSON として保存する。

    ファイル構造:
        output/pipeline_runs/<run_id>/
            raw_source_items.json
            reference_posts.json
            generation_jobs.json
            queue_items.json
            summary.json
    """

    def __init__(self, output_dir: str = _DEFAULT_OUTPUT_DIR) -> None:
        self.output_dir = Path(output_dir)

    def _run_dir(self, run_id: str) -> Path:
        return self.output_dir / run_id

    def save(
        self,
        run_id: str,
        stage: str,
        data: Any,
        dry_run: bool = True,
    ) -> str:
        """ステージ出力を保存する。dry_run=True の場合はパスのみ返す。"""
        path = self._run_dir(run_id) / f"{stage}.json"

        if dry_run:
            return f"[DRY_RUN] would save to {path}"

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return str(path)

    def save_summary(
        self,
        run_id: str,
        orchestrator_result: dict,
        dry_run: bool = True,
    ) -> str:
        """SourceToPostOrchestrator の結果サマリーを保存する。"""
        summary = {
            "run_id": run_id,
            "saved_at": datetime.utcnow().isoformat() + "Z",
            "account_id": orchestrator_result.get("account_id"),
            "platform": orchestrator_result.get("platform"),
            "steps": list(orchestrator_result.get("steps", {}).keys()),
            "summary": orchestrator_result.get("summary", {}),
            "safety": orchestrator_result.get("safety", {}),
        }
        return self.save(run_id, "summary", summary, dry_run=dry_run)

    def load(self, run_id: str, stage: str) -> Any:
        """保存済みステージデータを読み込む。"""
        path = self._run_dir(run_id) / f"{stage}.json"
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def list_runs(self) -> list[str]:
        """保存済み run_id の一覧を返す。"""
        if not self.output_dir.exists():
            return []
        return sorted(
            d.name for d in self.output_dir.iterdir() if d.is_dir()
        )
