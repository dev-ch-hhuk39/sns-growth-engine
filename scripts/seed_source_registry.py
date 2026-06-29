#!/usr/bin/env python3
"""source registry (default_sources.json) を source_accounts / reference_sources タブへ seed する。

過去にユーザーが共有済みのソースアカウントURL/選定ルールを回収して登録した
config/source_accounts/default_sources.json を真実源とし、
既存の正規化層 (recover_production_sheets_threads_first.source_rows) と
upsert層 (_upsert_many) を再利用して Sheets へ反映する。並行スキーマ/並行writerは作らない。

現フェーズ安全方針 (source_rows() が強制):
- 全 source: fetch_enabled=false / allow_download/cut/upload=false / auto_priority_change_allowed=false
- X: active=false / fetch_enabled=false / manual_only (reference source として保持・投稿/開発対象外)
- beauty (future_track=beauty_future, target=beauty_account): active=false / BLOCKED
- TikTok/YouTube: reuse_policy=reference_only / media_policy=do_not_download (can_reuse_media=false)
- status=WAITING_URL_INPUT: fetch 不可 (source_url 空)

使い方:
    python3 scripts/seed_source_registry.py --dry-run --target-account all --platform all
    python3 scripts/seed_source_registry.py --apply --confirm-seed --target-account all --platform all
    python3 scripts/seed_source_registry.py --dry-run --source-file config/source_accounts/my_sources.json

secret は一切表示しない。実 fetch / download / post は行わない。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_FILE = ROOT / "config/source_accounts/default_sources.json"

TARGET_CHOICES = ["night_scout", "liver_manager", "beauty_account", "beauty_future", "all"]
PLATFORM_CHOICES = ["threads", "x", "tiktok", "youtube", "instagram", "note", "manual_url", "query", "all"]


def _load_recover_module():
    spec = importlib.util.spec_from_file_location(
        "recover_production_sheets_threads_first",
        ROOT / "scripts/recover_production_sheets_threads_first.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _norm_url(u: str) -> str:
    import re
    if not u:
        return ""
    u = u.strip()
    u = re.sub(r"^http://", "https://", u)
    if not u.startswith("http"):
        u = "https://" + u
    u = u.split("?")[0].split("#")[0]
    u = re.sub(r"/+$", "", u)
    u = re.sub(r"^https://(www\.)?", "https://", u)
    return u.lower()


def _registry_status(row: dict) -> str:
    """source_url の有無/policy から registry status を導出。"""
    if not str(row.get("source_url", "")).strip():
        return "WAITING_URL_INPUT"
    if row.get("source_platform") == "x":
        return "MANUAL_REFERENCE_READY"
    if str(row.get("active", "")).lower() == "true":
        return "READY_FOR_REFERENCE_FETCH"
    return "MANUAL_REFERENCE_READY"


def _matches(row: dict, target: str, platform: str, raw_by_id: dict) -> bool:
    row_platform = row.get("source_platform") or row.get("platform")
    if platform != "all" and row_platform != platform:
        return False
    raw = raw_by_id.get(row.get("source_id"), {})
    row_targets = str(row.get("target_account_ids") or row.get("account_id") or "")
    raw_targets = raw.get("target_account_ids") or []
    if target == "all":
        return True
    if target == "beauty_future":
        return raw.get("future_track") == "beauty_future" or "beauty_account" in row_targets or "beauty_account" in raw_targets
    return target in row_targets or target in raw_targets


def _dedup(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """source_id / source_url / source_handle 重複を skip。"""
    seen_id: set = set()
    seen_url: dict = {}
    seen_handle: dict = {}
    kept, dropped = [], []
    for r in rows:
        sid = r.get("source_id")
        nu = _norm_url(r.get("source_url", ""))
        h = (r.get("source_platform"), str(r.get("source_handle", "")).lower())
        if sid in seen_id:
            dropped.append((sid, "dup_source_id")); continue
        if nu and nu in seen_url:
            dropped.append((sid, f"dup_source_url->{seen_url[nu]}")); continue
        if h[1] and h in seen_handle:
            dropped.append((sid, f"dup_handle->{seen_handle[h]}")); continue
        seen_id.add(sid)
        if nu:
            seen_url[nu] = sid
        if h[1]:
            seen_handle[h] = sid
        kept.append(r)
    return kept, dropped


def build_seed(source_file: Path, target: str, platform: str):
    mod = _load_recover_module()
    acc_rows, vid_rows = mod.source_rows(source_file)
    raw = json.loads(Path(source_file).read_text()).get("sources", [])
    raw_by_id = {s.get("source_id"): s for s in raw}

    acc = [r for r in acc_rows if _matches(r, target, platform, raw_by_id)]
    vid = [r for r in vid_rows if _matches(r, target, platform, raw_by_id)]
    acc, acc_dropped = _dedup(acc)
    vid, _ = _dedup(vid)
    for r in acc:
        r.setdefault("registry_status", _registry_status(r))
    return mod, acc, vid, acc_dropped, raw_by_id


def _summary(acc: list[dict], vid: list[dict], raw_by_id: dict) -> dict:
    import collections
    plat = collections.Counter(r["source_platform"] for r in acc)
    waiting = [r["source_id"] for r in acc if _registry_status(r) == "WAITING_URL_INPUT"]
    x_rows = [r for r in acc if r["source_platform"] == "x"]
    beauty = [
        r for r in acc
        if raw_by_id.get(r["source_id"], {}).get("future_track") == "beauty_future"
        or "beauty_account" in str(r.get("target_account_ids", ""))
    ]
    video = [r for r in acc if r["source_platform"] in ("tiktok", "youtube")]
    return {
        "total_source_accounts": len(acc),
        "total_reference_sources_video": len(vid),
        "by_platform": dict(plat),
        "active_true": sum(1 for r in acc if str(r.get("active", "")).lower() == "true"),
        "fetch_enabled_true": sum(1 for r in acc if str(r.get("fetch_enabled", "")).lower() == "true"),
        "x_manual_only": all(str(r.get("active", "")).lower() == "false" and str(r.get("fetch_enabled", "")).lower() == "false" for r in x_rows),
        "x_count": len(x_rows),
        "beauty_future_inactive": all(str(r.get("active", "")).lower() == "false" for r in beauty),
        "beauty_future_count": len(beauty),
        "beauty_target_account_id_preserved": all(
            "beauty_account" in str(r.get("target_account_ids", ""))
            and "beauty_future" not in str(r.get("target_account_ids", ""))
            for r in beauty
        ),
        "beauty_reference_only_safety": all(
            r.get("rights_policy") == "reference_only"
            and r.get("use_policy") == "REFERENCE_ONLY"
            and str(r.get("can_reuse_media", "")).lower() == "false"
            for r in beauty
        ),
        "video_reference_only": all(r.get("reuse_policy") == "reference_only" and r.get("allow_download") == "false" for r in video),
        "waiting_url_input": waiting,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="seed source registry to Sheets (safe, reference-only)")
    p.add_argument("--dry-run", action="store_true", help="差分を表示し Sheets へ書き込まない (既定)")
    p.add_argument("--apply", action="store_true", help="Sheets へ反映する (--confirm-seed 必須)")
    p.add_argument("--confirm-seed", action="store_true", help="--apply の確認フラグ")
    p.add_argument("--target-account", choices=TARGET_CHOICES, default="all")
    p.add_argument("--platform", choices=PLATFORM_CHOICES, default="all")
    p.add_argument("--source-file", default=str(DEFAULT_SOURCE_FILE))
    p.add_argument("--json", action="store_true", help="JSON サマリのみ出力")
    args = p.parse_args()

    source_file = Path(args.source_file)
    if not source_file.is_absolute():
        source_file = ROOT / source_file
    if not source_file.exists():
        print(json.dumps({"status": "ERROR", "reason": f"source-file not found: {source_file}"}, ensure_ascii=False))
        return 2

    mod, acc, vid, dropped, raw_by_id = build_seed(source_file, args.target_account, args.platform)
    summary = _summary(acc, vid, raw_by_id)
    summary["skipped_duplicates"] = len(dropped)
    summary["source_file"] = str(source_file.relative_to(ROOT)) if str(source_file).startswith(str(ROOT)) else str(source_file)
    summary["target_account"] = args.target_account
    summary["platform"] = args.platform

    do_apply = args.apply and args.confirm_seed
    summary["mode"] = "apply" if do_apply else "dry-run"

    if not do_apply:
        if args.json:
            print(json.dumps(summary, ensure_ascii=False))
        else:
            print("=== seed_source_registry DRY-RUN ===")
            for k, v in summary.items():
                print(f"  {k}: {v}")
            if dropped:
                print("  --- skipped (dedup) ---")
                for sid, why in dropped[:20]:
                    print(f"    {sid}: {why}")
            print("  (no Sheets write. use --apply --confirm-seed to seed)")
        if args.apply and not args.confirm_seed:
            print("  NOTE: --apply は --confirm-seed が無いため dry-run 扱い", file=sys.stderr)
        return 0

    # apply: 既存 SheetsClient + _upsert_many を再利用
    cfg = mod.get_config()
    client = mod.SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    client.setup_all()
    if hasattr(mod, "_refresh_ws_cache"):
        mod._refresh_ws_cache(client)
    ops = {}
    for logical, key, rows in (("source_accounts", "source_id", acc), ("reference_sources", "source_id", vid)):
        for attempt in range(5):
            try:
                ops[logical] = mod._upsert_many(client, logical, key, rows)
                break
            except Exception as e:  # noqa: BLE001  429/backoff
                wait = min(60, 2 ** attempt)
                print(f"  retry {logical} after {wait}s ({type(e).__name__})", file=sys.stderr)
                time.sleep(wait)
        else:
            print(json.dumps({"status": "ERROR", "reason": f"seed failed for {logical} after retries"}, ensure_ascii=False))
            return 1
    summary["applied_operations"] = ops
    print(json.dumps({"status": "APPLIED", **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
