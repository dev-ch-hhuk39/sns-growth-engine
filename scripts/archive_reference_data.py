#!/usr/bin/env python3
"""Archive sanitized reference data to local output or Sheets-compatible payloads."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = re.compile(r"(token|secret|cookie|authorization|password|api[_-]?key)", re.I)


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if SECRET_PATTERNS.search(str(k)) else sanitize(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value


def build_archive_payload(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "archive_id": f"arch_{kind}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "kind": kind,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "payload": sanitize(payload),
        "third_party_media_saved": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="archive reference data safely")
    parser.add_argument("--kind", default="raw_post_json", choices=["raw_post_json", "normalized_post_json", "transcript", "analysis", "clip_candidates", "generated_post_ideas"])
    parser.add_argument("--input-json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-archive", action="store_true")
    args = parser.parse_args()
    data = {}
    if args.input_json:
        data = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    payload = build_archive_payload(args.kind, data)
    if not args.apply:
        print(json.dumps({"status": "PLAN_ONLY", **payload}, ensure_ascii=False, indent=2))
        return 0
    if not args.confirm_archive:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-archive"}, ensure_ascii=False))
        return 1
    out_dir = ROOT / "output" / "reference_archive"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{payload['archive_id']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ARCHIVED", "path": str(path), "third_party_media_saved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
