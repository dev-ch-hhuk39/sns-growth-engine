#!/usr/bin/env python3
"""Free, local, no-post reference-only trend previews for manual review.

Uses exact pinned last30days commit, does not touch Google Sheets, paid APIs,
credentials, source media or any queue READY state. Japanese primary queries
may have no results; English general-category fallbacks remain labeled.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
STATE = Path.home() / ".cache" / "chadult-sns-source-research"
REPO = STATE / "last30days"
PIN = "249c7a4c040558a903d6838dee31012980d4946d"
PY = Path("/Library/Frameworks/Python.framework/Versions/3.13/bin/python3")
ACCOUNTS = ("night_scout", "liver_manager")
FALLBACKS = {
    "night_scout": "hospitality worker burnout customer service job",
    "liver_manager": "TikTok LIVE streamer engagement",
}
MAX_BYTES = 1_500_000
JST = timezone(timedelta(hours=9))
PRIVATE_ENV = (
    "TOKEN", "SECRET", "API_KEY", "PASSWORD", "COOKIE",
    "CREDENTIAL", "SA_JSON", "ACCESS_KEY", "AUTH",
)


class ResearchBlocked(Exception):
    """Never relay raw provider errors or untrusted text into logs."""


def pinned_script() -> Path:
    script = REPO / "skills/last30days/scripts/last30days.py"
    if not PY.is_file() or not script.is_file():
        raise ResearchBlocked("PINNED_RUNTIME_MISSING")
    result = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False, timeout=10,
    )
    if result.returncode != 0 or result.stdout.strip() != PIN:
        raise ResearchBlocked("PINNED_REVISION_MISMATCH")
    return script


def extract_json(output: str) -> dict:
    if len(output.encode("utf-8")) > MAX_BYTES:
        raise ResearchBlocked("PROVIDER_EXPORT_TOO_LARGE")
    decoder = json.JSONDecoder()
    matching = []
    for i, c in enumerate(output):
        if c != "{":
            continue
        try:
            data, _ = decoder.raw_decode(output[i:])
        except json.JSONDecodeError:
            continue
        if type(data) is dict and type(data.get("results")) is list and type(data.get("clusters")) is list:
            matching.append(data)
    if not matching:
        raise ResearchBlocked("PROVIDER_EXPORT_INVALID")
    return matching[-1]


def search(query: str, script: Path) -> dict:
    if len(query) > 140:
        raise ResearchBlocked("QUERY_TOO_LONG")
    env = {k: v for k, v in os.environ.items()
           if not any(fragment in k.upper() for fragment in PRIVATE_ENV)}
    env.update({
        "PUBLISH_ENABLED": "false",
        "ALLOW_REAL_THREADS_POST": "false",
        "ALLOW_REAL_X_POST": "false",
        "ALLOW_VIDEO_DOWNLOAD": "false",
        "ALLOW_VIDEO_CUT": "false",
        "ALLOW_CLOUDINARY_UPLOAD": "false",
        "ALLOW_MEDIA_POSTS": "false",
        "NO_COLOR": "1",
    })
    try:
        result = subprocess.run(
            [str(PY), str(script), query, "--emit=json", "--quick",
             "--days", "30", "--max-results", "10", "--no-browser-cookies"],
            cwd=STATE, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=False, timeout=170,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ResearchBlocked("PUBLIC_RESEARCH_EXECUTION_UNVERIFIED") from None
    if result.returncode != 0:
        raise ResearchBlocked("PUBLIC_RESEARCH_PROVIDER_FAILURE")
    return extract_json(result.stdout)


def evidence(results: list[dict], account: str, fallback: bool) -> list[dict]:
    output: list[dict] = []
    seen = set()
    for item in results[:30]:
        if type(item) is not dict:
            continue
        address = str(item.get("url") or "").strip()
        parsed = urlparse(address)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            continue
        if parsed.hostname in {"localhost", "127.0.0.1"} or parsed.hostname.endswith(".local"):
            continue
        if len(address) > 1000 or address in seen:
            continue
        seen.add(address)
        title = str(item.get("title") or "").strip()[:200]
        summary = str(item.get("summary") or "").strip()[:400]
        if not title:
            continue
        output.append({
            "candidate_id": "ref_" + hashlib.sha256(
                (account + "|" + address).encode("utf-8")).hexdigest()[:20],
            "account_id": account,
            "url": address,
            "title": title,
            "summary": summary,
            "source": str(item.get("source") or "")[:40],
            "status": "WAITING_REVIEW",
            "rights_policy": "reference_only",
            "media_policy": "do_not_download",
            "fallback_general_topic": fallback,
        })
        if len(output) >= 10:
            break
    return output


def run(script: Path, *, output_dir: Path) -> dict:
    topics = json.loads((ROOT / "config/research_topics.json").read_text(encoding="utf-8"))
    report = {
        "schema": "sns_local_reference_preview_v1",
        "generated_at": datetime.now(JST).isoformat(),
        "accounts": {},
        "posts": 0, "paid_ai": 0, "sheets_writes": 0,
    }
    for account in ACCOUNTS:
        configured = topics.get(account, [])
        if not isinstance(configured, list) or not configured:
            raise ResearchBlocked("PRIMARY_TOPICS_MISSING")
        primary = str(configured[0])
        fetched = search(primary, script)
        records = evidence(fetched["results"], account, False)
        fallback_used = False
        if not records:
            fallback_used = True
            fetched = search(FALLBACKS[account], script)
            records = evidence(fetched["results"], account, True)
        report["accounts"][account] = {
            "primary_query": primary,
            "fallback_query": FALLBACKS[account] if fallback_used else "",
            "status": "REFERENCES_PENDING_REVIEW" if records else "NO_PUBLIC_EVIDENCE",
            "evidence_count": len(records),
            "evidence": records,
        }
    if not output_dir.is_dir() or output_dir.is_symlink():
        raise ResearchBlocked("PRIVATE_PREVIEW_DIRECTORY_MISSING")
    if output_dir.stat().st_mode & 0o022:
        raise ResearchBlocked("PRIVATE_PREVIEW_DIRECTORY_UNSAFE")
    name = "daily-" + datetime.now(JST).strftime("%Y%m%d") + ".json"
    target = output_dir / name
    if target.is_symlink():
        raise ResearchBlocked("PREVIEW_DESTINATION_SYMLINK")
    fd, tmp = tempfile.mkstemp(prefix=".daily-preview.", suffix=".tmp", dir=output_dir)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
        fd_dir = os.open(output_dir, os.O_RDONLY)
        try:
            os.fsync(fd_dir)
        finally:
            os.close(fd_dir)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    counts = {account: int(r["evidence_count"]) for account,r in report["accounts"].items()}
    return {"status": "PASS" if sum(counts.values()) else "NO_PUBLIC_EVIDENCE",
            "accounts": counts, "total": sum(counts.values()),
            "posts": 0, "sheets_writes": 0, "paid_ai": 0}


def main() -> int:
    try:
        outcome = run(pinned_script(), output_dir=STATE / "previews")
        print("SNS_LOCAL_SOURCE_RESEARCH=" + json.dumps(outcome,sort_keys=True,separators=(",",":")))
        return 0 if outcome["status"] == "PASS" else 1
    except ResearchBlocked as exc:
        print("SNS_LOCAL_SOURCE_RESEARCH=" + json.dumps({
            "status": "BLOCKED", "reason": str(exc),
            "posts": 0, "paid_ai": 0,
        }, sort_keys=True,separators=(",",":")))
        return 1
    except Exception:
        print('SNS_LOCAL_SOURCE_RESEARCH={"status":"BLOCKED","reason":"UNVERIFIED_FAILURE","posts":0,"paid_ai":0}')
        return 1


if __name__ == "__main__":
    sys.exit(main())
