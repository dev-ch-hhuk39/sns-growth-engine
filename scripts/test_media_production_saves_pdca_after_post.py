#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("media_production", ROOT / "scripts" / "run_media_production_pipeline.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class Worksheet:
    def __init__(self, headers: list[str]) -> None:
        self.headers = headers
        self.rows: list[dict[str, str]] = []

    def row_values(self, _row: int) -> list[str]:
        return self.headers

    def get_all_records(self) -> list[dict[str, str]]:
        return list(self.rows)

    def append_row(self, values: list[str], **_kwargs: object) -> None:
        self.rows.append(dict(zip(self.headers, values)))


class FakeClient:
    def __init__(self) -> None:
        self.tabs = {name: Worksheet(headers) for name, headers in mod.TAB_DEFINITIONS.items()}

    def _ensure_tab(self, _name: str, _headers: list[str]) -> None:
        return None

    def _ws(self, name: str) -> Worksheet:
        return self.tabs[name]


def main() -> int:
    client = FakeClient()
    clip = {
        "clip_candidate_id": "clip-1", "account_id": "liver_manager",
        "public_post_text": "配信を始めたばかりなら、最初は話題を一つ決めて続けると入りやすい空気を作れます。",
        "hook_text": "初見が入りやすい配信", "duration_seconds": 20,
    }
    source_video = {"source_video_id": "sv-1"}
    post_result = {"result_id": "result-1", "queue_id": "queue-1", "post_url": "https://www.threads.com/@example/post/abc", "external_post_id": "abc"}
    first = mod._save_media_pdca_records(client, clip=clip, source_video=source_video, media_asset_id="asset-1", post_result=post_result)
    second = mod._save_media_pdca_records(client, clip=clip, source_video=source_video, media_asset_id="asset-1", post_result=post_result)
    media_result = client.tabs["media_post_results"].rows[0]
    metric = client.tabs["media_metrics"].rows[0]
    performance = client.tabs["clip_performance"].rows[0]
    checks = [
        ("first save creates all media PDCA rows", first == {"saved": 3, "skipped": 0}),
        ("second save deduplicates by clip", second == {"saved": 0, "skipped": 3}),
        ("media result links post and clip", media_result["result_id"] == "result-1" and media_result["clip_candidate_id"] == "clip-1"),
        ("metrics remain pending not fabricated", metric["metrics_status"] == "PENDING" and metric["views"] == ""),
        ("subtitle is explicitly disabled", performance["subtitle_style"] == "none"),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
