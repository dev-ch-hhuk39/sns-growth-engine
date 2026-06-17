#!/usr/bin/env python3
"""
import_posted_results.py - Posted Results Importer CLI（Phase 10）

手動/JSON/CSV/Sheetsから投稿結果を取り込む。
取り込んだデータはPDCAサイクルの入力として使う。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

JST = timezone(timedelta(hours=9))


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def load_from_json(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    for key in ("results", "posted_results", "items", "data"):
        if key in data and isinstance(data[key], list):
            return data[key]
    return [data]


def load_from_csv(path: str) -> list[dict]:
    results = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(dict(row))
    return results


def normalize_result(raw: dict, account_id: str) -> dict:
    def _int(v) -> int:
        try:
            return int(float(str(v).replace(",", "")))
        except Exception:
            return 0

    def _str(v) -> str:
        return str(v) if v is not None else ""

    return {
        "result_id": _str(raw.get("result_id", raw.get("post_id", raw.get("id", "")))),
        "account_id": _str(raw.get("account_id", account_id)),
        "platform": _str(raw.get("platform", "")),
        "post_id": _str(raw.get("post_id", raw.get("id", ""))),
        "post_url": _str(raw.get("post_url", raw.get("url", ""))),
        "posted_at": _str(raw.get("posted_at", raw.get("created_at", ""))),
        "content_type": _str(raw.get("content_type", raw.get("type", ""))),
        "generation_mode": _str(raw.get("generation_mode", raw.get("generation_type", ""))),
        "source_id": _str(raw.get("source_id", "")),
        "source_platform": _str(raw.get("source_platform", "")),
        "hook_style": _str(raw.get("hook_style", "")),
        "has_media": bool(raw.get("has_media", False)),
        "has_video": bool(raw.get("has_video", False)),
        "post_hour": _int(raw.get("post_hour", 0)),
        "like_count": _int(raw.get("like_count", raw.get("likes", 0))),
        "reply_count": _int(raw.get("reply_count", raw.get("replies", 0))),
        "repost_count": _int(raw.get("repost_count", raw.get("retweets", 0))),
        "bookmark_count": _int(raw.get("bookmark_count", raw.get("bookmarks", 0))),
        "impression_count": _int(raw.get("impression_count", raw.get("impressions", 0))),
        "view_count": _int(raw.get("view_count", raw.get("views", 0))),
        "imported_at": _now_jst(),
        "import_source": "json_import",
    }


def main():
    parser = argparse.ArgumentParser(description="Posted Results Importer")
    parser.add_argument("--account-id", default="night_scout")
    parser.add_argument("--input", default="", help="インポートファイル (JSON/CSV)")
    parser.add_argument("--output", help="正規化後のJSONを保存するパス")
    parser.add_argument("--mock", action="store_true", help="mock posted_results を使う")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"[import_posted_results] account={args.account_id} input={args.input}")

    if args.mock and not args.input:
        raw_results = [{
            "post_id": "mock_post_001",
            "platform": "x",
            "posted_at": _now_jst(),
            "text": "mock posted result",
            "likes": 12,
            "replies": 1,
            "reposts": 2,
            "impressions": 1000,
        }]
    elif not os.path.isfile(args.input):
        print(f"[ERROR] ファイルが見つかりません: {args.input}")
        sys.exit(1)
    else:
        ext = os.path.splitext(args.input)[1].lower()
        if ext == ".json":
            raw_results = load_from_json(args.input)
        elif ext == ".csv":
            raw_results = load_from_csv(args.input)
        else:
            print(f"[ERROR] 非対応形式: {ext}。.json または .csv を使用してください。")
            sys.exit(1)

    normalized = [normalize_result(r, args.account_id) for r in raw_results]

    print(f"[OK] {len(normalized)}件の投稿結果を読み込みました。")

    if args.dry_run:
        print("[DRY_RUN] 書き込みをスキップしました。")
        for r in normalized[:3]:
            print(f"  - {r['post_id']} ({r['platform']}) like={r['like_count']}")
        return 0

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump({"posted_results": normalized, "imported_at": _now_jst()}, f,
                      ensure_ascii=False, indent=2)
        print(f"[OK] 保存: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
