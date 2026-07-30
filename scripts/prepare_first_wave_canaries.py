#!/usr/bin/env python3
"""Prepare one exact four-item first wave without publishing.

The first wave is an atomic design contract, not four unrelated latest rows:
night_scout/original_text, night_scout/direct_image,
liver_manager/original_text, liver_manager/direct_image.
Dry-run never writes Sheets, uploads media, or posts. Apply requires an exact
batch id, an approved design-manifest hash, Cloudinary permission, and an
explicit confirmation phrase. It still never posts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from create_missing_text_canaries import _append as append_text_rows
from create_missing_text_canaries import build_rows as build_text_rows
from run_system_owned_media_canaries import apply_specs, build_specs

ACCOUNTS = ("night_scout", "liver_manager")
FIRST_WAVE_TYPES = ("original_text", "direct_image")
CONFIRMATION = "PREPARE_APPROVED_FIRST_WAVE"
MANIFEST_VERSION = "first_wave_manifest_v1"
SUPERSEDED_FIRST_WAVE_QUEUE_IDS = {
    "text_canary_fresh_20260729094318_night_scout_original_text",
    "q_fresh_night_scout_30440723109_direct_image",
    "text_canary_fresh_20260729094318_liver_manager_original_text",
    "q_fresh_liver_manager_30440723109_direct_image",
}


def _row_text(row: dict[str, Any]) -> str:
    return str(row.get("posted_text") or row.get("public_post_text") or row.get("text") or "").strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_payload(batch_id: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = []
    for item in sorted(candidates, key=lambda row: (str(row["account_id"]), str(row["content_type"]))):
        normalized.append({
            "account_id": item["account_id"],
            "content_type": item["content_type"],
            "canary_id": item["canary_id"],
            "batch_id": item["batch_id"],
            "public_post_text": item["public_post_text"],
            "primary_topic": item["primary_topic"],
            "structure_variant": str(item["structure_variant"]),
            "quality_gate_version": item["quality_gate_version"],
            "feature_schema_version": item.get("feature_schema_version", ""),
            "post_design": item.get("post_design", {}),
            "visual_plan": item.get("visual_plan", {}),
            "visual_text_hash": item.get("visual_text_hash", ""),
        })
    return {"manifest_version": MANIFEST_VERSION, "batch_id": batch_id, "candidates": normalized}


def _manifest_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text_candidate(row: dict[str, Any]) -> dict[str, Any]:
    design = json.loads(str(row.get("post_design_json") or "{}"))
    return {
        "account_id": str(row["account_id"]),
        "content_type": "original_text",
        "canary_id": str(row["canary_id"]),
        "queue_id": str(row["queue_id"]),
        "batch_id": str(row["batch_id"]),
        "public_post_text": str(row["public_post_text"]),
        "content_hash": str(row["content_hash"]),
        "primary_topic": str(row["primary_topic"]),
        "structure_variant": str(row["structure_variant"]),
        "quality_gate_version": str(row["quality_gate_version"]),
        "feature_schema_version": str(row.get("feature_schema_version", "")),
        "post_design": design,
        "visual_plan": {},
        "visual_text_hash": "",
        "quality": {key: row.get(key) for key in (
            "batch_diversity_status", "topic_coherence_status", "topic_confidence",
            "hook_topic_match", "closing_topic_match", "shared_hook_detected",
            "shared_closing_detected", "generation_attempt", "generation_rule_version",
        )},
        "registration_status": "READY_FOR_REGISTRATION",
    }


def _media_candidate(spec: dict[str, Any]) -> dict[str, Any]:
    files = [Path(value) for value in spec["files"]]
    return {
        "account_id": str(spec["post_design"]["account_id"]),
        "content_type": "direct_image",
        "canary_id": str(spec["canary_id"]),
        "queue_id": f"q_{spec['run_id']}_direct_image",
        "batch_id": str(spec["batch_id"]),
        "public_post_text": str(spec["text"]),
        "content_hash": hashlib.sha256(str(spec["text"]).encode("utf-8")).hexdigest(),
        "media_files": [str(path) for path in files],
        "media_content_hashes": [_sha(path) for path in files],
        "primary_topic": str(spec["quality"]["primary_topic"]),
        "structure_variant": str(spec["quality"]["structure_variant"]),
        "quality_gate_version": str(spec["quality"]["quality_gate_version"]),
        "feature_schema_version": str(spec["alignment"].get("feature_schema_version", "")),
        "post_design": spec["post_design"],
        "visual_plan": spec["visual_plan"],
        "visual_text_hash": str(spec["alignment"].get("visual_text_hash", "")),
        "quality": spec["quality"],
        "alignment": spec["alignment"],
        "registration_status": "READY_FOR_REGISTRATION",
    }


def _contract(batch_id: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: list[str] = []
    keys = {(str(row["account_id"]), str(row["content_type"])) for row in candidates}
    expected = {(account, kind) for account in ACCOUNTS for kind in FIRST_WAVE_TYPES}
    if keys != expected:
        reasons.append("exact_four_candidate_set_missing")
    if len(candidates) != 4:
        reasons.append("candidate_count_must_equal_four")
    if {str(row.get("batch_id", "")) for row in candidates} != {batch_id}:
        reasons.append("mixed_batch_ids")
    if len({str(row.get("canary_id", "")) for row in candidates}) != len(candidates):
        reasons.append("duplicate_canary_id")
    if len({str(row.get("content_hash", "")) for row in candidates}) != len(candidates):
        reasons.append("duplicate_public_text_hash")

    account_checks: dict[str, Any] = {}
    for account in ACCOUNTS:
        rows = [row for row in candidates if row["account_id"] == account]
        topics = {str(row.get("primary_topic", "")) for row in rows}
        structures = {str(row.get("structure_variant", "")) for row in rows}
        account_reasons: list[str] = []
        if len(topics) != 2:
            account_reasons.append("same_primary_topic_within_account")
        if len(structures) != 2:
            account_reasons.append("same_structure_variant_within_account")
        for row in rows:
            quality = row.get("quality", {})
            if str(quality.get("batch_diversity_status", "")).upper() != "PASS":
                account_reasons.append(f"{row['content_type']}:batch_diversity_not_pass")
            if str(quality.get("topic_coherence_status", "")).upper() != "PASS":
                account_reasons.append(f"{row['content_type']}:topic_coherence_not_pass")
            if row["content_type"] == "direct_image":
                alignment = row.get("alignment", {})
                if str(alignment.get("alignment_status", "")).upper() != "PASS":
                    account_reasons.append("direct_image:alignment_not_pass")
                if float(alignment.get("main_claim_coverage", 0)) < 1.0:
                    account_reasons.append("direct_image:claim_coverage_incomplete")
                if int(alignment.get("unsupported_claim_count", 1)) != 0:
                    account_reasons.append("direct_image:unsupported_claims")
                if alignment.get("visual_topic_match") is not True:
                    account_reasons.append("direct_image:visual_topic_mismatch")
                if alignment.get("visual_cta_match") is not True:
                    account_reasons.append("direct_image:visual_cta_mismatch")
        account_checks[account] = {
            "status": "PASS" if not account_reasons else "BLOCKED",
            "topics": sorted(topics),
            "structure_variants": sorted(structures),
            "reasons": sorted(set(account_reasons)),
        }
        reasons.extend(f"{account}:{reason}" for reason in account_reasons)

    media_hashes = [value for row in candidates for value in row.get("media_content_hashes", [])]
    if len(media_hashes) != len(set(media_hashes)):
        reasons.append("duplicate_media_content_hash")
    return {
        "status": "PASS" if not reasons else "BLOCKED",
        "expected_candidate_count": 4,
        "actual_candidate_count": len(candidates),
        "account_checks": account_checks,
        "blocked_reasons": sorted(set(reasons)),
    }


def build_first_wave(
    existing: list[dict[str, Any]],
    posted_results: list[dict[str, Any]],
    *,
    batch_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    generation_existing = [
        row for row in existing
        if str(row.get("batch_id", "")) != batch_id
        and str(row.get("queue_id", "")) not in SUPERSEDED_FIRST_WAVE_QUEUE_IDS
    ]
    text_rows: list[dict[str, Any]] = []
    media_specs: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for account in ACCOUNTS:
        text_result = build_text_rows(
            generation_existing,
            posted_results,
            targets=((account, "original_text"),),
            batch_id=batch_id,
        )
        if text_result.get("status") != "PLAN_ONLY" or len(text_result.get("rows", [])) != 1:
            return {"status": "TEXT_PREPARATION_BLOCKED", "batch_id": batch_id, "account_id": account, "detail": text_result, "would_post": False}
        text_row = dict(text_result["rows"][0])
        text_rows.append(text_row)
        text_candidate = _text_candidate(text_row)
        candidates.append(text_candidate)
        account_recent = [_row_text(row) for row in posted_results if str(row.get("account_id", "")) == account and _row_text(row)]
        specs = build_specs(
            account,
            output_dir,
            batch_id=batch_id,
            recent_posts=account_recent,
            kinds=("direct_image",),
            seed_batch_candidates=[text_row],
        )
        if len(specs) != 1:
            return {"status": "MEDIA_PREPARATION_BLOCKED", "batch_id": batch_id, "account_id": account, "would_post": False}
        media_specs.append(specs[0])
        candidates.append(_media_candidate(specs[0]))

    contract = _contract(batch_id, candidates)
    payload = _manifest_payload(batch_id, candidates)
    manifest_hash = _manifest_hash(payload)
    return {
        "status": "READY_FOR_FIRST_WAVE_APPLY" if contract["status"] == "PASS" else "FIRST_WAVE_CONTRACT_BLOCKED",
        "batch_id": batch_id,
        "manifest_version": MANIFEST_VERSION,
        "design_manifest_hash": manifest_hash,
        "contract": contract,
        "candidates": candidates,
        "manifest": payload,
        "text_rows": text_rows,
        "media_specs": media_specs,
        "would_write": False,
        "would_upload": False,
        "would_post": False,
    }


def _read_sheets(*, dry_run: bool) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]]]:
    from config_loader import get_config
    from sheets_client import SheetsClient, TAB_DEFINITIONS
    cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=dry_run)
    for logical in ("queue", "posted_results"):
        client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    return client, client._ws("queue").get_all_records(), client._ws("posted_results").get_all_records()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--expected-manifest-hash", default="")
    parser.add_argument("--confirm-first-wave", default="")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if not args.use_sheets:
        result = {"status": "BLOCKED", "reason": "--use-sheets is required", "would_post": False}
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 1
    if args.apply and (not args.batch_id or not args.expected_manifest_hash or args.confirm_first_wave != CONFIRMATION):
        result = {"status": "BLOCKED", "reason": "apply requires exact batch id, manifest hash, and PREPARE_APPROVED_FIRST_WAVE", "would_post": False}
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 1
    batch_id = args.batch_id or f"fresh_first_wave_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    if not re.fullmatch(r"fresh_[A-Za-z0-9_-]+", batch_id):
        result = {"status": "BLOCKED", "reason": "batch_id_must_start_with_fresh_and_use_safe_characters", "would_post": False}
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 1
    client, existing, posted = _read_sheets(dry_run=not args.apply)
    active_legacy = [
        str(row.get("queue_id", "")) for row in existing
        if str(row.get("queue_id", "")) in SUPERSEDED_FIRST_WAVE_QUEUE_IDS
        and str(row.get("status", "")).upper() != "SUPERSEDED_QUALITY"
    ]
    if args.apply and active_legacy:
        result = {
            "status": "BLOCKED",
            "reason": "legacy_first_wave_must_be_superseded_before_apply",
            "active_legacy_queue_ids": sorted(active_legacy),
            "would_post": False,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 1
    result = build_first_wave(existing, posted, batch_id=batch_id, output_dir=ROOT / "output/system_owned_media")
    internal_text_rows = result.pop("text_rows", [])
    internal_media_specs = result.pop("media_specs", [])
    if result.get("status") == "READY_FOR_FIRST_WAVE_APPLY" and args.apply:
        if result.get("design_manifest_hash") != args.expected_manifest_hash:
            result = {
                "status": "MANIFEST_MISMATCH",
                "batch_id": batch_id,
                "expected_manifest_hash": args.expected_manifest_hash,
                "actual_manifest_hash": result.get("design_manifest_hash", ""),
                "would_post": False,
            }
        elif os.environ.get("ALLOW_CLOUDINARY_UPLOAD", "").lower() != "true":
            result = {"status": "BLOCKED", "reason": "ALLOW_CLOUDINARY_UPLOAD=true required", "would_post": False}
        else:
            media_results = {}
            for account in ACCOUNTS:
                specs = [spec for spec in internal_media_specs if spec["post_design"]["account_id"] == account]
                media_results[account] = apply_specs(specs, account, upload=True)
            text_result = append_text_rows(client, internal_text_rows)
            success = text_result.get("status") == "APPLIED" and all(item.get("status") == "APPLIED" for item in media_results.values())
            result.update({
                "status": "APPLIED" if success else "PARTIAL_FAILURE",
                "media_registration": media_results,
                "text_registration": text_result,
                "would_write": True,
                "would_upload": True,
                "would_post": False,
            })
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["output_path"] = str(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"READY_FOR_FIRST_WAVE_APPLY", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
