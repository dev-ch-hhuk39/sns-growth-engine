#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
issues: list[str] = []
checks: list[str] = []

def require(condition: bool, message: str) -> None:
    if condition:
        checks.append(message)
    else:
        issues.append(message)

def content(relative: str) -> str:
    path = ROOT / relative
    require(path.exists(), f"file exists: {relative}")
    return path.read_text(encoding="utf-8") if path.exists() else ""

cfg_path = ROOT / "config/autonomous_mode.json"
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

for key in (
    "autonomous_mode_enabled",
    "auto_source_fetch_enabled",
    "auto_idea_generation_enabled",
    "auto_ready_enabled",
    "auto_post_enabled",
    "production_publish_activation_approved",
    "scheduled_prepare_enabled",
    "scheduled_publish_enabled",
):
    require(cfg.get(key) is True, f"autonomous config enabled: {key}")

require(cfg.get("kill_switch") is False, "kill switch is off")
require(cfg.get("report_only") is False, "report-only mode is off")
require(
    {"night_scout", "liver_manager", "beauty_account"}
    <= set(cfg.get("allowed_accounts", [])),
    "all three production accounts are allowed",
)
require(
    cfg.get("allowed_platforms_for_post") == ["threads"],
    "automatic posting platform is Threads only",
)
require(
    "x" in cfg.get("blocked_platforms_for_post", []),
    "X automatic posting is blocked",
)
require(cfg.get("allow_third_party_media") is False, "third-party media is globally blocked")
require(cfg.get("allow_unknown_rights") is False, "unknown-rights media is globally blocked")
require(cfg.get("allow_media_posts") is False, "global media posting stays fail-closed")

night = content(".github/workflows/autonomous-growth-loop-night-scout.yml")
for cron in ('45 4 * * *', '45 6 * * *', '45 15 * * *'):
    require(f'cron: "{cron}"' in night, f"Night Scout text cron: {cron}")
for slot in ("ns_1400_reference", "ns_1600_original", "ns_2500_pdca"):
    require(slot in night, f"Night Scout text slot: {slot}")
require('PUBLISH_ENABLED: "true"' in night, "Night Scout scheduled publisher can activate")
require('ALLOW_REAL_THREADS_POST: "true"' in night, "Night Scout real Threads path exists")
require('ALLOW_REAL_X_POST: "true"' not in night, "Night Scout scheduled X posting stays off")
require('ALLOW_MEDIA_POSTS: "true"' not in night, "Night Scout text workflow cannot post media")

liver = content(".github/workflows/autonomous-growth-loop-liver-manager.yml")
for cron in ('45 0 * * *', '45 3 * * *', '45 11 * * *'):
    require(f'cron: "{cron}"' in liver, f"Liver Manager text cron: {cron}")
for slot in ("lm_1000_original", "lm_1300_reference", "lm_2100_pdca"):
    require(slot in liver, f"Liver Manager text slot: {slot}")
require('PUBLISH_ENABLED: "true"' in liver, "Liver Manager scheduled publisher can activate")
require('ALLOW_REAL_THREADS_POST: "true"' in liver, "Liver Manager real Threads path exists")
require('ALLOW_REAL_X_POST: "true"' not in liver, "Liver Manager scheduled X posting stays off")
require('ALLOW_MEDIA_POSTS: "true"' not in liver, "Liver Manager text workflow cannot post media")

beauty = content(".github/workflows/beauty-threads-production.yml")
for cron in ('30 0 * * *', '30 9 * * *', '30 2 * * *', '30 11 * * *'):
    require(f'cron: "{cron}"' in beauty, f"Beauty cron: {cron}")
require("Save WAITING_REVIEW candidate" in beauty, "Beauty preparation remains human-review gated")
require("select_beauty_scheduled_ready.py" in beauty, "Beauty schedule selects explicit approved READY")
require("human_approved" in beauty, "Beauty scheduled publication requires human approval")
require('PUBLISH_ENABLED: "true"' in beauty, "Beauty approved publication can activate")
require('ALLOW_REAL_THREADS_POST: "true"' in beauty, "Beauty real Threads publisher exists")
require('ALLOW_REAL_X_POST: "true"' not in beauty, "Beauty X posting stays off")

night_direct = content(".github/workflows/direct-reference-media-night-scout.yml")
require('cron: "45 8 * * *"' in night_direct, "Night Scout Direct Media cron 17:45 JST")
require("ns_1800_direct_media" in night_direct, "Night Scout Direct Media slot")
require('PUBLISH_ENABLED: "true"' in night_direct, "Night Scout Direct Media publisher can activate")
require('ALLOW_REAL_THREADS_POST: "true"' in night_direct, "Night Scout Direct Media Threads path")
require('ALLOW_REAL_THREADS_VIDEO_POST: "true"' in night_direct, "Night Scout Direct video path")
require('ALLOW_MEDIA_POSTS: "true"' in night_direct, "Night Scout Direct media gate opens only in publish step")
require('ALLOW_REAL_X_POST: "true"' not in night_direct, "Night Scout Direct X posting stays off")

liver_direct = content(".github/workflows/direct-reference-media-liver-manager.yml")
require('cron: "45 6 * * *"' in liver_direct, "Liver Manager Direct Media cron 15:45 JST")
require("lm_1600_direct_media" in liver_direct, "Liver Manager Direct Media slot")
require('PUBLISH_ENABLED: "true"' in liver_direct, "Liver Manager Direct Media publisher can activate")
require('ALLOW_REAL_THREADS_POST: "true"' in liver_direct, "Liver Manager Direct Media Threads path")
require('ALLOW_REAL_THREADS_VIDEO_POST: "true"' in liver_direct, "Liver Manager Direct video path")
require('ALLOW_MEDIA_POSTS: "true"' in liver_direct, "Liver Manager Direct media gate opens only in publish step")
require('ALLOW_REAL_X_POST: "true"' not in liver_direct, "Liver Manager Direct X posting stays off")

media_scheduler = content(".github/workflows/media-preparation-scheduler.yml")
require('cron: "15 3 * * *"' in media_scheduler, "Direct inventory preparation cron 12:15 JST")
require('cron: "15 5 * * *"' in media_scheduler, "Beauty clip preparation cron 14:15 JST")
require("\n  push:\n" not in media_scheduler, "temporary acceptance push trigger removed")
require("TARGET_ACCOUNT: all" in media_scheduler, "scheduled Direct preparation targets all production accounts")
require("direct-media-preparation.yml/dispatches" in media_scheduler, "Direct preparation dispatcher connected")
require("approved-source-clip-preparation.yml/dispatches" in media_scheduler, "Beauty clip dispatcher connected")

direct_prepare = content(".github/workflows/direct-media-preparation.yml")
require("workflow_dispatch:" in direct_prepare, "Direct Media preparation dispatch endpoint exists")
require('PUBLISH_ENABLED: "false"' in direct_prepare, "Direct preparation cannot publicly post")
require('ALLOW_REAL_THREADS_POST: "false"' in direct_prepare, "Direct preparation Threads posting stays closed")
require('ALLOW_REAL_X_POST: "false"' in direct_prepare, "Direct preparation X posting stays closed")
require("acquire_approved_source_posts_failsoft.py" in direct_prepare, "Direct preparation refreshes approved inventory")
require("run_direct_media_preparation_loop.py" in direct_prepare, "Direct preparation bounded failover connected")
require("--max-assets\", \"10\"" in content("scripts/run_direct_media_preparation_loop.py"), "whole-parent media bundle cap is 10")

require((ROOT / ".github/workflows/approved-source-clip-preparation.yml").exists(), "Beauty approved-source clip workflow exists")

scheduled_workflows = "\n".join([
    night,
    liver,
    beauty,
    night_direct,
    liver_direct,
    media_scheduler,
])

require(
    'ALLOW_REAL_X_POST: "true"' not in scheduled_workflows,
    "no scheduled V1 workflow enables X posting",
)

payload = {
    "status": "PASS" if not issues else "FAIL",
    "passed_check_count": len(checks),
    "issues": issues,
}

print(json.dumps(payload, ensure_ascii=False, indent=2))
raise SystemExit(0 if not issues else 1)
